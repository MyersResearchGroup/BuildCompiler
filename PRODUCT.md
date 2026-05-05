# Product Brief: BuildCompiler Full-Build Refactor

## Problem

Synthetic biology users can design constructs in SBOL, but turning those designs into executable build workflows still requires manual reasoning about available inventory, missing parts, assembly levels, transformation, plating, and automation handoff formats.

BuildCompiler should act like a compiler: inspect abstract designs, resolve dependencies against inventory, choose an implementable route, generate missing intermediates when possible, and report actionable blockers when not possible.

## Target users

- Synthetic biology researchers designing constructs in SBOL/SBOLCanvas/SynBioSuite.
- Lab automation users generating manual or Opentrons-ready protocols through PUDU.
- Developers extending BuildCompiler's planning, inventory, SBOL, or protocol-generation behavior.
- AI coding agents such as Codex implementing scoped refactor tasks from an approved plan.

## Jobs to be done

1. As a researcher, I want to submit abstract SBOL designs and learn whether they can be built from available inventory.
2. As a build planner, I want missing level-1 engineered regions promoted into level-1 assembly requests.
3. As a build planner, I want missing promoter/RBS/CDS/terminator parts promoted into domestication requests.
4. As an automation user, I want SBOL and PUDU-compatible JSON outputs for assembly, transformation, and plating.
5. As a lab user, I want clear actions when a build is blocked by missing inventory, missing approvals, or unsupported designs.
6. As a developer, I want clear module boundaries so I can improve one stage without breaking the whole compiler.

## Product goals

- Make `full_build` a deterministic, inspectable compiler pipeline.
- Support partial success and structured blockers.
- Minimize new build work by searching inventory before generating new requests.
- Keep compiler-only mode lightweight and testable.
- Make optional automation outputs explicit, not default side effects.
- Provide a clean architecture that Codex can implement in small, safe increments.

## Non-goals

- Preserve old method signatures or module boundaries.
- Build a generic workflow engine.
- Make the reporting graph drive scheduling in v1.
- Implement DNA extraction as a real v1 stage.
- Automatically run Opentrons simulation.
- Silently mutate biological sequences without approval.
- Support arbitrary variable-length level-1 designs in v1.

## V1 scope

### Design classification

Initial abstract designs are classified as:

```text
ModuleDefinition
  -> assembly_lvl2

CombinatorialDerivation
  -> expand to concrete assembly_lvl1 variants

ComponentDefinition with >1 component
  -> assembly_lvl1

ComponentDefinition with <=1 component and supported role
  -> domestication

ComponentDefinition with <=1 component and unsupported role
  -> unsupported planning record
```

Supported level-1 roles for v1 are exactly:

```text
promoter, RBS, CDS, terminator
```

A valid level-1 concrete request contains exactly one promoter, one RBS, one CDS, and one terminator.

### Full-build behavior

`full_build` should use a bounded dependency-resolution loop:

```text
1. Try buildable level-2 requests.
2. Promote missing engineered regions to level-1 requests.
3. Try buildable level-1 requests.
4. Promote missing promoter/RBS/CDS/terminator parts to domestication requests.
5. Try domestication requests.
6. Index generated products.
7. Retry upward until success, no progress, failure, or max_iterations.
```

Successful assembly/domestication products are immediately chained to transformation and plating, deduplicated by product identity.

### Level-2 route optimization

Level-2 assembly expects a `ModuleDefinition` with engineered regions as components. If `region_order` is supplied, it is a hard constraint. If no order is supplied, the planner searches possible engineered-region orders up to the default exhaustive bound of 4 regions.

Primary objective:

```text
minimize number of new level-1 plasmids required
```

Tie-breakers:

1. Respect hard constraints.
2. Prefer existing collection plasmids over generated/planned plasmids.
3. Prefer higher material state.
4. Prefer fewer total assemblies.
5. Tie-break by stable ordered SBOL identities.

The detailed report should include the selected route and top 3 rejected alternatives.

### Level-1 route optimization

Level-1 assembly uses SBOL order when unambiguous. If SBOL order differs from promoter/RBS/CDS/terminator, warn the user but respect SBOL order. If order is ambiguous, enforce canonical promoter/RBS/CDS/terminator order.

Primary objective:

```text
minimize number of new domestications required
```

Tie-breakers mirror level-2 route selection.

### Domestication

Domestication produces a domesticated plasmid as the primary product. Edited inserts and internal BsaI-site edits are provenance/artifacts, not primary products.

Compiler-only mode may propose sequence edits and record them. Protocol/execution mode must block unless the relevant process is approved.

### Reporting

Every `FullBuildResult` includes a lightweight `BuildSummary`. A comprehensive `BuildReport` is generated only when `options.reporting.include_detailed_report=True`.

The detailed report should include:

- status
- executive summary
- stage sections
- selected routes
- rejected alternatives
- missing inputs
- required approvals
- warnings
- next immediate actions
- full dependency chain
- graph summary

## Success criteria

V1 is successful when:

- The new architecture exists with the target package boundaries.
- `BuildCompiler.plan(...)` classifies designs and expands valid combinatorial variants.
- `BuildCompiler.execute(...)` runs a bounded dependency loop with mocked/stubbed stages.
- Level-1 assembly is ported behind the new `AssemblyService` interface.
- Level-1 and level-2 route optimizers return selected routes plus structured blockers.
- Domestication reports sequence-edit approvals and missing backbones correctly.
- Compiler-only mode returns SBOL artifacts and PUDU-compatible JSON intermediates without PUDU/Opentrons.
- Transform/plating chaining deduplicates by product identity.
- `FullBuildResult.summary` always exists and `FullBuildResult.report` is opt-in.
- Core tests run under pytest + Ruff without optional automation dependencies.

## Future considerations

- DNA extraction as a real material-state transition.
- Larger level-2 search strategies beyond exhaustive order enumeration.
- Variable-length level-1 constructs.
- Persistent approval files.
- Rich SynBioSuite UI integration for route alternatives, build graph, and approvals.
- Stronger SBOL validation and provenance visualization.
