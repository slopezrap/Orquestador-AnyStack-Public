from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from orchestrator.common import compiled_dir, memory_dir, now_iso, project_root, write_json, write_yaml

ID_PREFIXES = "ARC|PRJ|BB|DR|DI|UC|ALG|J|PG|PERM|SM|ERR|INT|SCR|VIEW|EVT|DATA|VER|ADR|AD|RISK|CFG|EXT|SLICE|API|WORKER|FU|REP|HANDOFF"
ID_RE = re.compile(rf"\b(?:{ID_PREFIXES})-[A-Za-z0-9_.:-]+\b")
FENCE_RE = re.compile(r"```(?:yaml\s+orchestrator|orchestrator)\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _line_start_offsets(text: str) -> list[int]:
    offsets = [0]
    for m in re.finditer(r"\n", text):
        offsets.append(m.end())
    return offsets


def _line_for_pos(offsets: list[int], pos: int) -> int:
    # tiny binary search without importing bisect in hot hooks
    lo, hi = 0, len(offsets)
    while lo < hi:
        mid = (lo + hi) // 2
        if offsets[mid] <= pos:
            lo = mid + 1
        else:
            hi = mid
    return max(1, lo)


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower()).strip("-")
    return slug or "section"


def extract_sections(text: str) -> list[dict[str, Any]]:
    matches = list(HEADING_RE.finditer(text))
    offsets = _line_start_offsets(text)
    sections: list[dict[str, Any]] = []
    heading_stack: list[tuple[int, str]] = []
    for idx, m in enumerate(matches, start=1):
        level = len(m.group(1))
        title = m.group(2).strip()
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, title))
        start = m.start()
        end = matches[idx].start() if idx < len(matches) else len(text)
        section_text = text[start:end].rstrip()
        line_start = _line_for_pos(offsets, start)
        line_end = _line_for_pos(offsets, end)
        sections.append({
            "section_id": f"SEC-{idx:04d}",
            "level": level,
            "title": title,
            "anchor": slugify(title),
            "line_start": line_start,
            "line_end": line_end,
            "heading_path": [h[1] for h in heading_stack],
            "char_count": len(section_text),
            "sha256": sha256_text(section_text),
            "id_refs": sorted(set(ID_RE.findall(section_text))),
            "excerpt": re.sub(r"\s+", " ", section_text[:600]).strip(),
        })
    if not sections:
        sections.append({
            "section_id": "SEC-0001",
            "level": 1,
            "title": "BLUEPRINT",
            "anchor": "blueprint",
            "line_start": 1,
            "line_end": text.count("\n") + 1,
            "heading_path": ["BLUEPRINT"],
            "char_count": len(text),
            "sha256": sha256_text(text),
            "id_refs": sorted(set(ID_RE.findall(text))),
            "excerpt": re.sub(r"\s+", " ", text[:600]).strip(),
        })
    return sections


def extract_blocks(text: str) -> list[dict[str, Any]]:
    offsets = _line_start_offsets(text)
    blocks: list[dict[str, Any]] = []
    for idx, m in enumerate(FENCE_RE.finditer(text), start=1):
        raw = m.group(1).strip("\n")
        kind = "unknown"
        km = re.search(r"^\s*kind\s*:\s*['\"]?([^'\"\n#]+)", raw, flags=re.MULTILINE)
        if km:
            kind = km.group(1).strip().lower()
        blocks.append({
            "block_id": f"BLOCK-{idx:04d}",
            "block_index": idx,
            "kind": kind,
            "line_start": _line_for_pos(offsets, m.start()),
            "line_end": _line_for_pos(offsets, m.end()),
            "sha256": sha256_text(raw),
            "ids": sorted(set(ID_RE.findall(raw))),
            "raw_yaml": raw,
        })
    return blocks


def index_ids_to_sections(sections: list[dict[str, Any]], blocks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_id: dict[str, list[dict[str, Any]]] = {}
    for sec in sections:
        for iid in sec.get("id_refs") or []:
            by_id.setdefault(str(iid), []).append({
                "section_id": sec.get("section_id"),
                "title": sec.get("title"),
                "anchor": sec.get("anchor"),
                "line_start": sec.get("line_start"),
                "line_end": sec.get("line_end"),
                "sha256": sec.get("sha256"),
            })
    block_refs: dict[str, list[dict[str, Any]]] = {}
    for block in blocks:
        for iid in block.get("ids") or []:
            block_refs.setdefault(str(iid), []).append({
                "block_id": block.get("block_id"),
                "block_index": block.get("block_index"),
                "kind": block.get("kind"),
                "line_start": block.get("line_start"),
                "line_end": block.get("line_end"),
                "sha256": block.get("sha256"),
            })
    # Prefer nearby sections, but keep all section mentions.  Attach block_refs where available.
    for iid, refs in by_id.items():
        seen = set()
        deduped = []
        for ref in refs:
            key = (ref.get("section_id"), ref.get("line_start"), ref.get("line_end"))
            if key not in seen:
                seen.add(key)
                nr = dict(ref)
                if iid in block_refs:
                    nr["blocks"] = block_refs[iid]
                deduped.append(nr)
        by_id[iid] = deduped
    for iid, refs in block_refs.items():
        by_id.setdefault(iid, [])
        if not by_id[iid]:
            by_id[iid].append({"section_id": None, "title": None, "anchor": None, "line_start": None, "line_end": None, "blocks": refs})
    return by_id


def create_lossless_context(blueprint_path: Path) -> dict[str, Any]:
    bp = blueprint_path.resolve()
    text = bp.read_text(encoding="utf-8")
    sections = extract_sections(text)
    blocks = extract_blocks(text)
    ids_to_sections = index_ids_to_sections(sections, blocks)
    cdir = compiled_dir()
    cdir.mkdir(parents=True, exist_ok=True)
    snapshot_path = cdir / "BLUEPRINT.snapshot.md"
    snapshot_path.write_text(text, encoding="utf-8")
    manifest = {
        "schema_version": "1.0",
        "generated_at": now_iso(),
        "source": {
            "path": str(blueprint_path),
            "resolved_path": str(bp),
            "sha256": sha256_text(text),
            "line_count": text.count("\n") + 1,
            "char_count": len(text),
        },
        "lossless_contract": {
            "full_text_snapshot": "orchestrator-state/compiled/BLUEPRINT.snapshot.md",
            "manifest_json": "orchestrator-state/compiled/blueprint-manifest.json",
            "sections_json": "orchestrator-state/compiled/blueprint-sections.json",
            "blocks_json": "orchestrator-state/compiled/blueprint-blocks.json",
            "lossless_json": "orchestrator-state/compiled/blueprint-lossless.json",
        },
        "section_count": len(sections),
        "orchestrator_block_count": len(blocks),
        "ids_indexed": len(ids_to_sections),
        "ids_to_sections": ids_to_sections,
    }
    lossless = {"manifest": manifest, "sections": sections, "blocks": blocks, "ids_to_sections": ids_to_sections}
    write_json(cdir / "blueprint-manifest.json", manifest)
    write_yaml(cdir / "blueprint-manifest.yaml", manifest)
    write_json(cdir / "blueprint-sections.json", {"sections": sections})
    write_yaml(cdir / "blueprint-sections.yaml", {"sections": sections})
    write_json(cdir / "blueprint-blocks.json", {"blocks": blocks})
    write_yaml(cdir / "blueprint-blocks.yaml", {"blocks": blocks})
    write_json(cdir / "blueprint-lossless.json", lossless)
    write_yaml(cdir / "blueprint-lossless.yaml", lossless)
    return manifest


def enrich_orchestrator_input(compiled: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    source_map = compiled.setdefault("source_map", {})
    ids_to_sections = manifest.get("ids_to_sections") or {}
    compiled["blueprint"] = manifest
    for iid, refs in ids_to_sections.items():
        if iid in source_map and isinstance(source_map[iid], dict):
            source_map[iid]["source_sections"] = refs
    return compiled


def mirror_lossless_to_memory() -> None:
    cdir = compiled_dir()
    mdir = memory_dir()
    mdir.mkdir(parents=True, exist_ok=True)
    for name in ["blueprint-manifest", "blueprint-sections", "blueprint-blocks", "blueprint-lossless"]:
        for suffix in ["json", "yaml"]:
            src = cdir / f"{name}.{suffix}"
            if src.exists():
                shutil.copyfile(src, mdir / src.name)
