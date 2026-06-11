from __future__ import annotations
import json, re, sys
from pathlib import Path
from typing import Any

from orchestrator.common import compiled_dir, project_root, read_json, read_yaml, registry_path, tasks_dir
from orchestrator.runtime.state_machine import state_machine_errors
from orchestrator.runtime.memory_yaml import check_memory_yaml

MIN_DESCRIPTION_CHARS = 240
MIN_SPEC_DESCRIPTION_CHARS = 240
MIN_DEPENDENCY_RATIONALE_CHARS = 180
REQUIRED_LOGIC = ["domain", "application", "journey", "permission", "state", "error", "integration", "ui"]
REQUIRED_AUXILIARY = ["arc42", "data", "config", "verification", "adr", "risks", "glossary", "external_refs"]
REQUIRED_SLICE_FIELDS = ["id","title","description","dependency_rationale","depends_on_rationale","dependency_edges","phase","type","implements","builds","verifies","risk","verify_mode","depends_on","write_set","conflict_group","building_block_refs"]
REQUIRED_TASK_FIELDS = ["schema_version","id","task_id","title","description","dependency_rationale","depends_on_rationale","dependency_edges","resolved_dependencies","phase_id","step_id","order","type","status","depends_on","dependents","implements","builds","closes_journeys","journey_refs","arc42_refs","write_set","read_set","conflict_group","conflict_groups","building_block_refs","verification_refs","risk","risk_level","verify_mode","verification_surface","acceptance","evidence_contract","contract_refs","resolved_specs","source_refs","generated_from","locks","parallel"]
REQUIRED_DAG_NODE_FIELDS = [field for field in REQUIRED_TASK_FIELDS if field not in {"schema_version", "resolved_specs", "source_refs", "generated_from"}]
FORBIDDEN = [
    re.compile(r"\b(?:TODO|TBD|FIXME|XXX|foo|bar|baz)\b|(?i:\b(?:lorem\s+ipsum|placeholder|monkey|foo|bar|baz|xxx)\b)"),
    re.compile(r"\b(?:dummy|fake|stubbed|stub\s+implementation|temporary\s+implementation|fake\s+data|mock\s+data|sample\s+data|seed\s+data|hardcoded\s+demo)\b", re.I),
    re.compile(r"\bNotImplementedError\b|^\s*pass\s*(?:#.*)?$", re.I | re.M),
    re.compile(r"It carries arc42 intent into resolved_specs|This dependency rationale is part of (?:the )?(?:production )?DAG contract|without reinterpreting prose or falling back to secondary documents", re.I),
]


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def role_contract() -> dict[str, Any]:
    c = read_json(project_root()/'.claude'/'orchestrator-contract.json', {})
    return ((c.get('trailer_schema') or {}).get('roles') or {})


def schema_required(path: Path, trail: list[str]) -> list[str]:
    d = read_json(path, {})
    cur: Any = d
    for key in trail:
        if isinstance(cur, dict):
            cur = cur.get(key, {})
        else:
            return []
    return list(cur.get('required') or []) if isinstance(cur, dict) else []


def schema_status_enum(path: Path, trail: list[str]) -> list[str]:
    d = read_json(path, {})
    cur: Any = d
    for key in trail:
        if isinstance(cur, dict):
            cur = cur.get(key, {})
        else:
            return []
    if isinstance(cur, dict):
        return list(cur.get('enum') or [])
    return []


def first_keys(obj: dict[str, Any], keys: list[str]) -> list[str]:
    return [k for k in obj.keys() if k in keys]


def check_text(task_id: str, field: str, value: Any, refs: list[str]) -> list[str]:
    text = norm(value)
    errors: list[str] = []
    if not text:
        errors.append(f'{task_id}: missing {field}')
        return errors
    if field == 'description':
        if len(text) < MIN_DESCRIPTION_CHARS:
            errors.append(f'{task_id}: description shorter than {MIN_DESCRIPTION_CHARS}')
    for pat in FORBIDDEN:
        if pat.search(text):
            errors.append(f'{task_id}: {field} contains non-production or unfinished wording')
    return errors


def main() -> int:
    root = project_root()
    errors: list[str] = []
    warnings: list[str] = []
    # Packaging/runtime hygiene: durable lifecycle events belong under
    # orchestrator-state/tasks/lifecycle-events/. A root-level tasks/ tree is a
    # stale build artifact and can confuse humans reviewing PR payloads, even if
    # the runtime ignores it. Keep this check here so future packages cannot
    # accidentally ship orphan lifecycle signals outside orchestrator-state.
    orphan_tasks = root / 'tasks'
    if orphan_tasks.exists():
        errors.append('root-level tasks/ directory is not allowed; use orchestrator-state/tasks/ instead')

    sm = read_yaml(root/'orchestrator/rules/state-machine.yaml', {})
    statuses = set((sm.get('statuses') or {}).keys())
    roles = role_contract()
    errors.extend(state_machine_errors(roles))
    # Contract/status/schema alignment.
    mutating = {r for r,s in roles.items() if s.get('mutates_registry_lifecycle')}
    info = {r for r,s in roles.items() if s.get('info_only') or not s.get('mutates_registry_lifecycle')}
    trans = sm.get('transitions') or {}
    for role in mutating:
        if role not in trans:
            errors.append(f'{role}: mutating contract role lacks state-machine transitions')
    for role in info:
        if role in trans:
            errors.append(f'{role}: info-only contract role must not mutate lifecycle')
        # NEXT_STATUS metadata is allowed for info-only roles; it just must name known statuses.
        for st in roles.get(role, {}).get('next_status_values') or []:
            if st not in statuses:
                errors.append(f'{role}: metadata NEXT_STATUS {st} not in state-machine statuses')
    for role, spec in roles.items():
        for st in spec.get('next_status_values') or []:
            if st and st not in statuses:
                errors.append(f'{role}: contract NEXT_STATUS {st} not in state-machine statuses')
    # Schema required fields.
    schema_paths = [root/'orchestrator/schemas/orchestrator-input.schema.json', root/'.claude/schemas/orchestrator-input.schema.json']
    for p in schema_paths:
        required = schema_required(p, ['properties','slices','items'])
        for field in REQUIRED_SLICE_FIELDS:
            if field not in required:
                errors.append(f'{p.relative_to(root)}: slices[] does not require {field}')
    for p in [root/'orchestrator/schemas/registry.schema.json', root/'.claude/schemas/registry.schema.json']:
        required = schema_required(p, ['properties','tasks','items'])
        for field in REQUIRED_TASK_FIELDS:
            if field not in required:
                errors.append(f'{p.relative_to(root)}: tasks[] does not require {field}')
        enum = schema_status_enum(p, ['properties','tasks','items','properties','status'])
        if set(enum) != statuses:
            errors.append(f'{p.relative_to(root)}: status enum does not match state-machine statuses')
    for p in [root/'orchestrator/schemas/task-dag.schema.json', root/'.claude/schemas/task-dag.schema.json']:
        required = schema_required(p, ['properties','nodes','items'])
        for field in REQUIRED_DAG_NODE_FIELDS:
            if field not in required:
                errors.append(f'{p.relative_to(root)}: nodes[] does not require {field}')
        enum = schema_status_enum(p, ['properties','nodes','items','properties','status'])
        if set(enum) != statuses:
            errors.append(f'{p.relative_to(root)}: node status enum does not match state-machine statuses')
    # Runtime artifacts.
    inp = read_json(compiled_dir()/ 'orchestrator-input.json', {})
    reg = read_json(registry_path(), {})
    dag = read_json(tasks_dir()/ 'task-dag.json', {})
    if not inp:
        errors.append('missing compiled orchestrator-input.json')
    else:
        for key in REQUIRED_LOGIC:
            if not (inp.get('logic') or {}).get(key):
                errors.append(f'orchestrator-input missing logic.{key}')
        if not inp.get('building_blocks'):
            errors.append('orchestrator-input missing building_blocks')
        for key in REQUIRED_AUXILIARY:
            if not (inp.get('auxiliary') or {}).get(key):
                errors.append(f'orchestrator-input missing auxiliary.{key}')

        expected_blueprint = norm(__import__('os').environ.get('ORCHESTRATOR_EXPECT_BLUEPRINT', 'inputs/BLUEPRINT.md'))
        actual_blueprint = norm((inp.get('compiler') or {}).get('blueprint_path'))
        if expected_blueprint and actual_blueprint != expected_blueprint:
            errors.append(f'orchestrator-input compiled from {actual_blueprint or "<missing>"}, expected active blueprint {expected_blueprint}')
        # Every machine-readable contract item must include a detailed description.
        def _iter_machine_items():
            for bb in inp.get('building_blocks', []) or []:
                yield 'building_blocks', bb
            for bucket, items in (inp.get('logic') or {}).items():
                for item in items or []:
                    yield f'logic.{bucket}', item
            for bucket, items in (inp.get('auxiliary') or {}).items():
                for item in items or []:
                    yield f'auxiliary.{bucket}', item
        for kind, item in _iter_machine_items():
            if not isinstance(item, dict):
                continue
            iid = str(item.get('id') or kind)
            desc = norm(item.get('description') or item.get('summary'))
            if not desc:
                errors.append(f'{iid}: {kind} missing detailed description')
            elif len(desc) < MIN_SPEC_DESCRIPTION_CHARS:
                errors.append(f'{iid}: {kind} description shorter than {MIN_SPEC_DESCRIPTION_CHARS}')
            for field in ['name','title','description']:
                if item.get(field):
                    errors.extend(check_text(iid, field, item.get(field), []))
    if dag:
        for field in ['parallelism', 'parallel_groups', 'lock_model']:
            if field not in dag:
                errors.append(f'task-dag missing {field}')
        par = dag.get('parallelism') or {}
        if par:
            try:
                if int(par.get('max_parallel_slices') or 0) < 1:
                    errors.append('task-dag parallelism.max_parallel_slices must be >= 1')
            except Exception:
                errors.append('task-dag parallelism.max_parallel_slices must be integer')
            if par.get('lock_backend') != 'posix_fcntl_file_locks':
                errors.append('task-dag parallelism.lock_backend must be posix_fcntl_file_locks')
        if dag.get('parallel_groups'):
            task_ids_in_groups = {str(tid) for g in dag.get('parallel_groups') or [] for tid in (g.get('task_ids') or [])}
            node_ids = {str(n.get('id')) for n in dag.get('nodes') or [] if n.get('id')}
            if task_ids_in_groups != node_ids:
                errors.append('task-dag parallel_groups do not cover exactly all nodes')
    slices = {str(s.get('id')): s for s in inp.get('slices', []) or [] if s.get('id')}
    tasks = {str(t.get('id')): t for t in reg.get('tasks', []) or [] if t.get('id')}
    nodes = {str(n.get('id')): n for n in dag.get('nodes', []) or [] if n.get('id')}
    if set(slices) != set(tasks):
        errors.append('registry task IDs differ from compiled slice IDs')
    if set(slices) != set(nodes):
        errors.append('task-dag node IDs differ from compiled slice IDs')
    symbols = set()
    for bb in inp.get('building_blocks', []) or []:
        if isinstance(bb, dict) and bb.get('id'): symbols.add(str(bb['id']))
    for bucket in (inp.get('logic') or {}).values():
        for item in bucket or []:
            if isinstance(item, dict) and item.get('id'): symbols.add(str(item['id']))
    for bucket in (inp.get('auxiliary') or {}).values():
        for item in bucket or []:
            if isinstance(item, dict) and item.get('id'): symbols.add(str(item['id']))
    symbols.update(slices)
    for sid, sl in sorted(slices.items()):
        refs = [str(x) for key in ('implements','builds','verifies','closes_journeys','depends_on') for x in (sl.get(key) or [])]
        for ref in refs:
            if ref not in symbols:
                errors.append(f'{sid}: unresolved slice ref {ref}')
        errors.extend(check_text(sid, 'title', sl.get('title'), refs))
        errors.extend(check_text(sid, 'description', sl.get('description'), refs))
        drat = norm(sl.get('dependency_rationale'))
        if not drat or len(drat) < MIN_DEPENDENCY_RATIONALE_CHARS:
            errors.append(f'{sid}: missing detailed dependency_rationale')
        dep_map = sl.get('depends_on_rationale') or {}
        if not isinstance(dep_map, dict):
            errors.append(f'{sid}: depends_on_rationale must be an object')
            dep_map = {}
        deps = [str(x) for x in sl.get('depends_on') or []]
        for dep in deps:
            reason = norm(dep_map.get(dep))
            if not reason or len(reason) < MIN_DEPENDENCY_RATIONALE_CHARS:
                errors.append(f'{sid}: missing detailed depends_on_rationale for {dep}')
        extra_dep_rationale = sorted(set(str(k) for k in dep_map) - set(deps))
        if extra_dep_rationale:
            errors.append(f'{sid}: depends_on_rationale contains non-dependency keys {extra_dep_rationale}')
        dep_edges = sl.get('dependency_edges') or []
        if len(dep_edges) != len(deps):
            errors.append(f'{sid}: dependency_edges count does not match depends_on')
        for edge in dep_edges:
            if edge.get('to') != sid or edge.get('from') not in deps or len(norm(edge.get('reason'))) < MIN_DEPENDENCY_RATIONALE_CHARS:
                errors.append(f'{sid}: invalid dependency edge {edge}')
        if norm(sl.get('title')).lower() == norm(sl.get('description')).lower():
            errors.append(f'{sid}: description duplicates title')
        task = tasks.get(sid)
        node = nodes.get(sid)
        for name, obj in [('registry task', task), ('dag node', node)]:
            if not obj:
                errors.append(f'{sid}: missing {name}')
                continue
            if obj.get('title') != sl.get('title') or norm(obj.get('description')) != norm(sl.get('description')):
                errors.append(f'{sid}: {name} title/description drift from orchestrator-input')
            if norm(obj.get('dependency_rationale')) != drat:
                errors.append(f'{sid}: {name} dependency_rationale drift from orchestrator-input')
            if obj.get('depends_on_rationale') != dep_map:
                errors.append(f'{sid}: {name} depends_on_rationale drift from orchestrator-input')
            if obj.get('dependency_edges') != dep_edges:
                errors.append(f'{sid}: {name} dependency_edges drift from orchestrator-input')
            locks = obj.get('locks') or {}
            if not locks:
                errors.append(f'{sid}: {name} missing locks')
            else:
                for lk in ['task','write_set','conflict_groups','lock_files']:
                    if lk not in locks:
                        errors.append(f'{sid}: {name} locks missing {lk}')
                for lf in locks.get('lock_files') or []:
                    if '\\' in str(lf) or not str(lf).endswith('.lock'):
                        errors.append(f'{sid}: {name} has non-POSIX or non-lock lock file {lf}')
            parallel = obj.get('parallel') or {}
            if not parallel or not parallel.get('safe_group'):
                errors.append(f'{sid}: {name} missing parallel.safe_group')
            surface = obj.get('verification_surface') or {}
            if not isinstance(surface, dict) or not surface:
                errors.append(f'{sid}: {name} missing verification_surface')
            else:
                for key in ['kind','method','requires_visual_mcp','requires_screen_journey_reviewer','journey_refs_are_ui_signals','rationale','evidence_route','minimum_runtime_proof']:
                    if key not in surface:
                        errors.append(f'{sid}: {name} verification_surface missing {key}')
                if obj.get('journey_refs') and not surface.get('ui_spec_refs') and not surface.get('route_refs') and not (surface.get('signals') or {}).get('ui_write_paths'):
                    if surface.get('requires_visual_mcp') or surface.get('requires_screen_journey_reviewer') or surface.get('journey_refs_are_ui_signals'):
                        errors.append(f'{sid}: {name} treats journey_refs without UI route as UI verification surface')
                    if surface.get('kind') != 'journey_backend_contract':
                        errors.append(f'{sid}: {name} journey_refs without UI route must be journey_backend_contract')
                if surface.get('requires_visual_mcp') and surface.get('kind') not in {'browser_ui','mobile_ui'}:
                    errors.append(f'{sid}: {name} requires visual MCP for non-UI surface {surface.get("kind")}')
            surface = obj.get('verification_surface') or {}
            if not isinstance(surface, dict) or not surface:
                errors.append(f'{sid}: {name} missing verification_surface')
            else:
                surface_kind = str(surface.get('kind') or '')
                if surface.get('journey_refs') and not surface.get('ui_spec_refs') and not surface.get('route_refs') and not (surface.get('signals') or {}).get('ui_write_paths'):
                    if surface.get('requires_visual_mcp') or surface.get('requires_screen_journey_reviewer'):
                        errors.append(f'{sid}: {name} treats backend journey_refs as UI verification surface')
                    if surface_kind != 'journey_backend_contract':
                        errors.append(f'{sid}: {name} journey_refs without UI must classify as journey_backend_contract, got {surface_kind}')
                if surface.get('requires_visual_mcp') and not (surface.get('ui_spec_refs') or surface.get('route_refs') or (surface.get('signals') or {}).get('ui_write_paths')):
                    errors.append(f'{sid}: {name} requires visual MCP without UI spec or route')
                matrix = surface.get('evidence_matrix') or []
                if not surface.get('requires_visual_mcp'):
                    if not isinstance(matrix, list) or not matrix:
                        errors.append(f'{sid}: {name} non-UI verification_surface missing evidence_matrix')
                    elif not any(isinstance(m, dict) and m.get('required') for m in matrix):
                        errors.append(f'{sid}: {name} non-UI evidence_matrix has no required categories')
                if not surface.get('minimum_runtime_proof'):
                    errors.append(f'{sid}: {name} verification_surface missing minimum_runtime_proof')
            if name == 'registry task':
                resolved = obj.get('resolved_specs') or []
                if not resolved:
                    errors.append(f'{sid}: registry task missing resolved_specs')
                for spec in resolved:
                    if len(norm(spec.get('description'))) < MIN_SPEC_DESCRIPTION_CHARS:
                        errors.append(f"{sid}: resolved spec {spec.get('id')} missing detailed description")
                    if not isinstance(spec.get('raw'), dict) or not spec.get('raw'):
                        errors.append(f"{sid}: resolved spec {spec.get('id')} missing raw YAML payload")
                    if not isinstance(spec.get('details'), dict):
                        errors.append(f"{sid}: resolved spec {spec.get('id')} missing details payload")
                    if not isinstance(spec.get('source_ref'), dict):
                        errors.append(f"{sid}: resolved spec {spec.get('id')} missing source_ref payload")
                rdeps = obj.get('resolved_dependencies') or []
                if len(rdeps) != len(deps):
                    errors.append(f'{sid}: registry task resolved_dependencies count does not match depends_on')
                for dep in rdeps:
                    if dep.get('id') not in deps or len(norm(dep.get('description'))) < MIN_DESCRIPTION_CHARS:
                        errors.append(f"{sid}: resolved dependency {dep.get('id')} missing detailed description")
            seq = first_keys(obj, ['id','task_id','title','description','phase_id'])
            try:
                ti = seq.index('title'); di = seq.index('description')
                if di != ti + 1:
                    errors.append(f'{sid}: {name} description must be immediately after title in JSON order')
            except ValueError:
                errors.append(f'{sid}: {name} lacks title/description order check fields')
        pack_json = read_json(tasks_dir()/ 'task-packs' / f'{sid}.json', {})
        pack_md = tasks_dir()/ 'task-packs' / f'{sid}.md'
        if norm(pack_json.get('description')) != norm(sl.get('description')):
            errors.append(f'{sid}: task-pack JSON description drift')
        if norm(pack_json.get('dependency_rationale')) != drat:
            errors.append(f'{sid}: task-pack JSON dependency_rationale drift')
        if pack_json.get('depends_on_rationale') != dep_map:
            errors.append(f'{sid}: task-pack JSON depends_on_rationale drift')
        if pack_json.get('dependency_edges') != dep_edges:
            errors.append(f'{sid}: task-pack JSON dependency_edges drift')
        if len(pack_json.get('resolved_dependencies') or []) != len(deps):
            errors.append(f'{sid}: task-pack JSON resolved_dependencies count mismatch')
        if not pack_json.get('resolved_specs'):
            errors.append(f'{sid}: task-pack JSON missing resolved_specs')
        if not pack_md.exists():
            errors.append(f'{sid}: missing task-pack markdown')
        else:
            text = pack_md.read_text(encoding='utf-8', errors='replace')
            if norm(sl.get('description')) not in norm(text):
                errors.append(f'{sid}: task-pack markdown missing description')
            for phrase in ['CLAUDE_TRAILER:', 'Developer success:', 'Tester pass:', 'Verifier success:', '## Dependency edges', '## Resolved dependency tasks']:
                if phrase not in text:
                    errors.append(f'{sid}: task-pack markdown missing {phrase}')
    # Template completeness.
    tpl = root/'docs/templates/blueprint-smoke/BLUEPRINT.template.md'
    if tpl.exists():
        text = tpl.read_text(encoding='utf-8', errors='replace')
        for kind in ['project','stack','auxiliary.arc42','building_blocks','logic.domain','logic.application','logic.journey','logic.permission','logic.state','logic.error','logic.integration','logic.ui','auxiliary.data','auxiliary.config','auxiliary.verification','auxiliary.adr','auxiliary.risks','auxiliary.glossary','auxiliary.external_refs','registry.slices']:
            if f'kind: {kind}' not in text:
                errors.append(f'template missing kind: {kind}')
    else:
        errors.append('missing docs/templates/blueprint-smoke/BLUEPRINT.template.md')
    mem = check_memory_yaml()
    if not mem.get('ok'):
        errors.extend(f"memory_yaml: {e}" for e in mem.get('errors', []))
    warnings.extend(f"memory_yaml: {w}" for w in mem.get('warnings', []))
    result = {'ok': not errors, 'slices': len(slices), 'registry_tasks': len(tasks), 'dag_nodes': len(nodes), 'memory_yaml': mem, 'errors': sorted(set(errors)), 'warnings': warnings}
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 2


if __name__ == '__main__':
    raise SystemExit(main())
