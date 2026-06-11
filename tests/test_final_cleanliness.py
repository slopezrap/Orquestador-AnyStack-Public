from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".py", ".sh"}
FORBIDDEN_TOKENS = [
    "leg" + "acy",
    "refa" + "ctor",
    "migratio" + "n report",
    "Orquestado" + "rBlueprint",
    "AnyPl" + "atform",
    "orchestr" + "ator-And",
    "AndS" + "tack",
    "ands" + "tack",
    "Option" + "s Heat",
    "Mas" + "sive",
    "IB" + "KR",
    "Interacti" + "ve Brokers",
    "FI" + "NRA",
    "score_mode" + "l_versions",
    "RET" + "IRED",
    "0.1.2-l" + "ossless",
    "compiler" + "_version",
    "skills-an" + "d-commands",
    "command" + "-runtime",
    "old-" + "rule",
    ".claude/" + "commands/",
]


def iter_project_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.name == "test_final_cleanliness.py":
            continue
        yield path


def test_final_package_identity_and_schema_ids_are_anystack():
    # CI checkout directories are chosen by the host repository name, not by the
    # packaged runtime identity. Keep this test independent from paths such as
    # Orquestador-AnyStack-Public while still enforcing the public runtime name.
    assert (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[0] == "# orchestrator-AnyStack"
    assert 'name = "orchestrator-anystack"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert not (ROOT / ".claude" / "commands").exists()
    for schema in (ROOT / ".claude" / "schemas").glob("*.json"):
        data = json.loads(schema.read_text(encoding="utf-8"))
        sid = str(data.get("$id", ""))
        if sid.startswith("orchestrator."):
            assert sid.startswith("orchestrator.anystack."), schema


def test_final_package_has_no_historical_or_app_specific_residue():
    offenders: list[str] = []
    for path in iter_project_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in FORBIDDEN_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(ROOT)}: {token}")
    assert offenders == []
