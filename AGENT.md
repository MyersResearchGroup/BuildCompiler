# Agent Guide for BuildCompiler

## Mission

Codex should implement the BuildCompiler clean-architecture refactor in small, verifiable increments. The goal is not to preserve legacy APIs. The current repository is inspiration and evidence, especially for level-1 assembly and SBOL digestion/ligation behavior.

## Role split

### ChatGPT owns

- Reducing ambiguity.
- Revising architecture and product decisions.
- Breaking work into milestones and tasks.
- Deciding between alternatives when requirements conflict.
- Reviewing whether Codex output matches the intended plan.
- Updating this guidance when product or architecture decisions change.

### Codex owns

- Creating and editing repository files.
- Implementing scoped tasks.
- Refactoring within approved boundaries.
- Adding tests.
- Running checks.
- Reporting assumptions, blockers, and deviations.

When a decision changes architecture, product scope, biological behavior, or public API semantics, Codex should stop and ask ChatGPT/user for a decision before continuing.

## Hard rules

1. Prefer small, incremental changes.
2. Keep the project runnable after every task.
3. Write tests for non-trivial logic.
4. Update docs when architecture, behavior, or commands change.
5. Do not preserve legacy APIs unless explicitly requested.
6. Do not add compatibility wrappers.
7. Do not silently expand scope.
8. Do not hide assumptions.
9. Do not make PUDU or Opentrons required for core tests.
10. Do not run Opentrons simulation by default.
11. Do not silently mutate biological sequences.
12. Do not silently assume reagent purchase.
13. Keep domain contracts identity-based where possible.
14. Keep raw `sbol2` objects at inventory/SBOL/stage boundaries.
15. Use `SbolResolver` instead of scattered direct SBOL document lookup.
16. Use structured blockers, warnings, and approvals instead of raw exceptions for expected build issues.
17. Raise unexpected implementation errors by default.

## Definition of a safe Codex task

A task is safe for Codex when it has:

- A clear target file or module.
- A clear expected behavior.
- A test strategy.
- No unresolved product or architecture tradeoff.
- No need to choose between incompatible biological semantics.

Examples:

- Add `StageStatus`, `BuildStatus`, and tests.
- Implement `BuildOptions` dataclasses.
- Create `SbolResolver` with `PullPolicy.NEVER` unit tests.
- Add `Inventory.add_generated_product()` and indexing tests.
- Port `Assembly` behind `AssemblyService` without changing internals.

## Definition of a risky task

A task is risky when it:

- Changes public API semantics.
- Changes build-stage behavior.
- Changes approval or sequence-edit policy.
- Changes route-selection ranking.
- Changes material-state semantics.
- Touches PUDU/Opentrons execution side effects.
- Requires choosing how SBOL structures should be interpreted.
- Would take more than one focused PR.

Risky tasks should be decomposed or escalated to ChatGPT/user.

## Handoff protocol

Every Codex task should begin with:

```text
Task goal:
Files expected to change:
Behavior expected:
Tests expected:
Known constraints:
```

Every Codex completion should report:

```text
Implemented:
Tests added/updated:
Commands run:
Assumptions made:
Blockers or follow-up tasks:
```

If tests cannot be run, Codex must say why and identify the smallest command that should be run later.

## Implementation sequence

Implement in milestone order. Do not jump directly to the full-build loop before contracts and tests exist.

### Milestone 1: Domain contracts and options

Create:

```text
src/buildcompiler/domain/
src/buildcompiler/api/options.py
```

Add contracts for:

- `BuildStage`
- `StageStatus`
- `BuildStatus`
- `MaterialState`
- `BuildRequest`
- `StageResult`
- `FullBuildResult`
- `MissingBuildInput`
- `RequiredApproval`
- `BuildWarning`
- `IndexedPlasmid`
- `IndexedBackbone`
- `IndexedReagent`
- `BuildOptions` and focused option groups

Tests:

```text
tests/unit/domain/
tests/unit/api/test_options.py
```

### Milestone 2: SBOL resolver and inventory

Create:

```text
src/buildcompiler/sbol/resolver.py
src/buildcompiler/inventory/
```

Implement:

- `PullPolicy`
- `SbolResolver`
- normalized inventory records
- eager indexes
- generated-product indexing
- reagent lookup
- backbone lookup

Tests should use offline SBOL fixtures and `PullPolicy.NEVER`.

### Milestone 3: Planner and classification

Create:

```text
src/buildcompiler/planning/classifier.py
src/buildcompiler/planning/combinatorial.py
src/buildcompiler/planning/full_build_planner.py
src/buildcompiler/planning/validation.py
```

Implement classification rules:

```text
ModuleDefinition -> assembly_lvl2
CombinatorialDerivation -> expanded assembly_lvl1 requests
ComponentDefinition >1 component -> assembly_lvl1
ComponentDefinition <=1 component with supported role -> domestication
ComponentDefinition <=1 component unsupported -> unsupported
```

Implement combinatorial cap and invalid variant warnings.

### Milestone 4: Compatibility selector and route models

Create:

```text
src/buildcompiler/inventory/selector.py
src/buildcompiler/inventory/compatibility.py
```

Implement route scoring dataclasses for level-1 and level-2. Keep scores explicit, not opaque numbers.

### Milestone 5: SBOL assembly service and level-1 stage

Port current working `Assembly` behavior into:

```text
src/buildcompiler/sbol/assembly.py
```

Wrap it with:

```text
src/buildcompiler/stages/assembly_lvl1.py
```

Do not deeply refactor SBOL internals until tests protect the new service interface.

### Milestone 6: Domestication stage

Create:

```text
src/buildcompiler/sbol/domestication.py
src/buildcompiler/stages/domestication.py
```

Implement:

- supported role validation
- missing backbone handling
- missing reagent handling
- sequence edit proposals
- approval-gated execution behavior
- domesticated plasmid output

### Milestone 7: Level-2 stage

Create:

```text
src/buildcompiler/stages/assembly_lvl2.py
```

Implement:

- `ModuleDefinition` engineered-region extraction
- optional `region_order` constraint
- exhaustive order search up to 4 regions
- missing level-1 promotion
- selected route and top rejected alternatives

### Milestone 8: Full-build executor

Create:

```text
src/buildcompiler/execution/full_build_executor.py
src/buildcompiler/execution/worklist.py
src/buildcompiler/execution/stage_runner.py
src/buildcompiler/execution/context.py
```

Implement bounded retry loop with mocked/stubbed stages first, then wire real stages.

### Milestone 9: Transformation and plating

Create:

```text
src/buildcompiler/stages/transformation.py
src/buildcompiler/stages/plating.py
src/buildcompiler/sbol/transformation.py
```

Implement SBOL transformation records, PUDU JSON intermediates, plate mapping, and deduplication.

### Milestone 10: Adapters, reporting, and integration tests

Create:

```text
src/buildcompiler/adapters/pudu/
src/buildcompiler/adapters/opentrons/
src/buildcompiler/reporting/
```

Implement:

- assembly/transformation/plating JSON adapters
- optional manual/automated protocol file generation
- optional Opentrons simulation wrapper
- `BuildSummary`
- opt-in `BuildReport`
- reporting-only `BuildGraph`
- end-to-end happy-path fixture test

## Testing and verification expectations

Use pytest and Ruff for default CI.

Core commands:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Fallback without `uv`:

```bash
ruff check .
ruff format --check .
pytest
```

Automation-specific tests should be marked and optional:

```bash
pytest -m automation
```

Suggested test layout:

```text
tests/
  unit/
    domain/
    planning/
    inventory/
    execution/
    reporting/
  stages/
    test_assembly_lvl1.py
    test_domestication.py
    test_assembly_lvl2.py
    test_transformation.py
    test_plating.py
  integration/
    test_full_build_happy_path.py
    test_full_build_missing_lvl1_then_domestication.py
  automation/
    test_pudu_json_adapters.py
    test_opentrons_simulation_smoke.py
  fixtures/
    sbol/
    expected_json/
```

## Documentation update rules

Update docs in the same PR when:

- public API changes
- package layout changes
- option defaults change
- stage behavior changes
- status semantics change
- approval behavior changes
- route scoring changes
- test commands or CI commands change

## ADR trigger conditions

Create or update an ADR when:

- There are multiple reasonable architecture options.
- A decision changes module boundaries.
- A decision changes biological interpretation.
- A decision changes public API.
- A decision adds or removes a stage.
- A decision changes default safety behavior.
- A decision adds persistent side effects.

## Progress reporting style

Codex should keep progress compact and evidence-based:

```text
Done:
- Added domain status enums and tests.
- Added BuildOptions groups with defaults.

Verified:
- uv run pytest tests/unit/domain tests/unit/api
- uv run ruff check src tests

Assumptions:
- MaterialState.PLANNED ranks below ASSEMBLED and above missing material.

Next:
- Implement SbolResolver with PullPolicy.NEVER tests.
```

## When to stop and ask

Stop and ask ChatGPT/user before:

- Changing approval semantics.
- Changing level-1 cardinality.
- Supporting new part roles.
- Changing level-2 route scoring.
- Making graph scheduling drive execution.
- Making PUDU/Opentrons required.
- Adding persistent approvals.
- Adding DNA extraction as a real stage.
