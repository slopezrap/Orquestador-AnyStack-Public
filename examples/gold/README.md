# Gold Blueprint fixture

This fixture is the canonical blueprint-first acceptance example for the orchestrator. It contains arc42 sections plus machine-readable `yaml orchestrator` blocks for project, stack, auxiliary.arc42, building_blocks, Domain Logic, Application Logic, Journey, Permission Logic, State Logic, Error Logic, Integration Logic, UI Logic, Data, Config, Verification, ADR, Risks, Glossary, External References and Registry Slices.

Run:

```bash
./scripts/compile-blueprint.sh examples/gold/BLUEPRINT.md
./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
./scripts/check-gold-blueprint.sh examples/gold/BLUEPRINT.md
```
