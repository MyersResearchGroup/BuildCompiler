# BuildCompiler Architecture

## System overview

BuildCompiler is a Python compiler pipeline for synthetic biology build planning. It takes SBOL designs and biological inventory, then produces structured build plans, SBOL build artifacts, PUDU-compatible JSON intermediates, and optional protocol-generation artifacts.

The architecture separates:

```text
planning: classify and expand what should be built
execution: decide what to run and retry
stages: perform biological build operations
inventory: answer what material exists
sbol: construct and resolve SBOL objects
adapters: translate BuildCompiler outputs to external formats
reporting: explain what happened and what to do next
```

## Design principles

1. **Compiler first, automation second.** Core planning and SBOL/JSON generation should run without PUDU or Opentrons.
2. **Contracts before implementation.** Domain dataclasses define stable boundaries between planner, executor, stages, inventory, and reporting.
3. **Partial success is normal.** Stages may produce some products while reporting missing inputs or approvals.
4. **Expected blockers are data.** Missing plasmids, backbones, reagents, approvals, and unsupported designs should be structured records.
5. **Unexpected bugs are errors.** Implementation errors should raise by default unless `continue_on_error=True`.
6. **Inventory and selection are separate.** Inventory answers what exists; selectors decide which valid route to use.
7. **SBOL identity is canonical.** Domain models should use SBOL identities as stable keys. Raw `sbol2` objects stay at inventory/SBOL/stage boundaries.
8. **The graph explains; it does not schedule.** The v1 build graph is reporting-only.

## Package structure

```text
src/buildcompiler/
  api/          Public user API and options
  domain/       Pure contracts and normalized domain models
  planning/     Classification, validation, combinatorial expansion
  execution/    Worklist, context, bounded full-build loop
  stages/       Domestication, lvl1, lvl2, transformation, plating
  sbol/         SBOL construction, resolver, document helpers
  inventory/    Indexes, SynBioHub loading, compatibility selection
  adapters/     PUDU JSON/protocol and Opentrons simulation adapters
  reporting/    Build graph, summary, detailed report, serialization
  errors.py
  logging.py
```

## Public API

`BuildCompiler.__init__` is dependency-injected and lightweight:

```python
compiler = BuildCompiler(
    inventory=inventory,
    sbol_document=doc,
    planner=FullBuildPlanner(),
    executor=FullBuildExecutor(),
    adapters=AdapterRegistry(...),
)
```

Convenience construction handles SynBioHub loading and indexing:

```python
compiler = BuildCompiler.from_synbiohub(
    collections=collections,
    sbh_registry=sbh_registry,
    auth_token=auth_token,
    sbol_doc=sbol_doc,
)
```

Primary workflow:

```python
plan = compiler.plan(abstract_designs)
result = compiler.execute(plan)
```

Convenience wrapper:

```python
result = compiler.full_build(abstract_designs, options=options)
```

## Core domain model

### Status enums

```python
class StageStatus(Enum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    BLOCKED = "blocked"
    FAILED = "failed"

class BuildStatus(Enum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
```

`BLOCKED` means expected inputs or approvals can unblock the stage later. `FAILED` means the request cannot proceed without changing the design, options, collections, or approval state.

### BuildRequest

```python
@dataclass
class BuildRequest:
    id: str
    stage: BuildStage
    source_identity: str
    source_display_id: str | None
    source_kind: DesignKind
    parent_group: str | None = None
    variant_index: int | None = None
    constraints: dict = field(default_factory=dict)
```

Core contracts should use SBOL identities and normalized metadata. Stages resolve identities to raw SBOL objects through `SbolResolver`.

### StageResult

```python
@dataclass
class StageResult:
    id: str
    stage: BuildStage
    status: StageStatus
    request_ids: list[str]
    products: list[IndexedPlasmid]
    missing_inputs: list[MissingBuildInput]
    required_approvals: list[RequiredApproval]
    warnings: list[BuildWarning]
    sbol_document: sbol2.Document | None
    json_intermediate: dict | list | None
    protocol_artifacts: dict
    logs: list[str]
```

### FullBuildResult

```python
@dataclass
class FullBuildResult:
    status: BuildStatus
    plan: BuildPlan
    build_document: sbol2.Document
    stage_results: list[StageResult]
    graph: BuildGraph
    final_products: list[IndexedPlasmid]
    missing_inputs: list[MissingBuildInput]
    required_approvals: list[RequiredApproval]
    warnings: list[BuildWarning]
    summary: BuildSummary
    report: BuildReport | None = None
```

### MissingBuildInput

```python
@dataclass
class MissingBuildInput:
    source_stage: BuildStage
    source_design_identity: str
    missing_identity: str
    missing_display_id: str | None
    missing_kind: Literal[
        "engineered_region",
        "promoter",
        "rbs",
        "cds",
        "terminator",
        "backbone",
        "restriction_enzyme",
        "ligase",
    ]
    required_stage: BuildStage | Literal["fatal"]
    reason: str
    candidates_tried: list[str] = field(default_factory=list)
```

### RequiredApproval

Approvals should be easy to grant by process name.

```python
@dataclass
class RequiredApproval:
    status: ApprovalStatus
    process: str
    reason: str
    metadata: dict = field(default_factory=dict)

@dataclass
class ApprovalOptions:
    approved_processes: set[str] = field(default_factory=set)
    approved_approval_ids: set[str] = field(default_factory=set)
    scope: Literal["run", "persistent"] = "run"
```

Default approval scope is run-scoped.

## Options model

Use composed option groups:

```python
@dataclass
class BuildOptions:
    planning: PlanningOptions = field(default_factory=PlanningOptions)
    execution: ExecutionOptions = field(default_factory=ExecutionOptions)
    selection: SelectionOptions = field(default_factory=SelectionOptions)
    protocol: ProtocolOptions = field(default_factory=ProtocolOptions)
    reporting: ReportingOptions = field(default_factory=ReportingOptions)
    approvals: ApprovalOptions = field(default_factory=ApprovalOptions)
    reagents: ReagentOptions = field(default_factory=ReagentOptions)
    domestication: DomesticationOptions = field(default_factory=DomesticationOptions)
```

Important defaults:

```python
ExecutionOptions(max_iterations=5, continue_on_error=False)
ProtocolOptions(mode=ProtocolMode.NONE, simulate=False, results_dir=None)
ReportingOptions(include_detailed_report=False, include_rejected_routes=True, max_rejected_routes=3)
CombinatorialOptions(max_variants=256, allow_large_expansion=False)
Lvl2SearchOptions(max_exhaustive_region_count=4, allow_large_order_search=False)
ReagentOptions(allow_reagent_purchase=False, default_restriction_enzyme="BsaI", default_ligase="T4_DNA_ligase")
```

## BuildContext

Every stage receives one explicit typed context:

```python
@dataclass
class BuildContext:
    sbol: SbolResolver
    inventory: Inventory
    build_document: sbol2.Document
    options: BuildOptions
    adapters: AdapterRegistry
    graph: BuildGraph
    logger: BuildLogger
```

Stage signature:

```python
def run(request: BuildRequest, context: BuildContext) -> StageResult:
    ...
```

## SBOL resolver

Stages should not call `doc.get(...)`, `doc.find(...)`, or SynBioHub pull logic directly. Use `SbolResolver`.

```python
class SbolResolver:
    def get_component(self, identity: str) -> sbol2.ComponentDefinition: ...
    def get_module(self, identity: str) -> sbol2.ModuleDefinition: ...
    def get_combinatorial_derivation(self, identity: str) -> sbol2.CombinatorialDerivation: ...
    def get_implementation(self, identity: str) -> sbol2.Implementation: ...
    def maybe_pull(self, identity: str) -> object: ...
```

Pull policy:

```python
class PullPolicy(Enum):
    NEVER = "never"
    MISSING_ONLY = "missing_only"
    ALWAYS_REFRESH = "always_refresh"
```

Default to `MISSING_ONLY`; use `NEVER` for deterministic offline tests.

## Inventory architecture

Inventory owns normalized records and eager indexes.

### IndexedPlasmid

```python
@dataclass
class IndexedPlasmid:
    identity: str
    display_id: str
    definition: sbol2.ComponentDefinition
    implementations: list[sbol2.Implementation]
    strain_definitions: list[sbol2.ModuleDefinition]
    strain_implementations: list[sbol2.Implementation]
    insert_identities: set[str]
    fusion_sites: tuple[str, ...]
    antibiotic_resistance: str | None
    source: Literal["collection", "generated"]
    generating_stage: BuildStage | None
    material_state: MaterialState
    provenance: dict
```

### IndexedBackbone and IndexedReagent

```python
@dataclass
class IndexedBackbone:
    identity: str
    display_id: str
    definition: sbol2.ComponentDefinition
    implementations: list[sbol2.Implementation]
    fusion_sites: tuple[str, ...]
    antibiotic_resistance: str | None
    material_state: MaterialState
    source: Literal["collection", "generated"]
    provenance: dict

@dataclass
class IndexedReagent:
    identity: str
    display_id: str
    name: str
    kind: Literal["restriction_enzyme", "ligase", "other"]
    definition: sbol2.ComponentDefinition
    implementations: list[sbol2.Implementation]
    source: Literal["collection", "generated", "assumed_purchase"]
    provenance: dict
```

### Inventory facade

```python
class Inventory:
    plasmids_by_identity: dict[str, IndexedPlasmid]
    plasmids_by_insert_identity: dict[str, list[IndexedPlasmid]]
    plasmids_by_fusion_sites: dict[tuple[str, ...], list[IndexedPlasmid]]
    plasmids_by_antibiotic: dict[str, list[IndexedPlasmid]]
    backbones_by_fusion_sites_and_antibiotic: dict[tuple[tuple[str, ...], str], list[IndexedBackbone]]

    def find_single_part_plasmids(self, part_identity: str, *, antibiotic: str | None = None) -> list[IndexedPlasmid]: ...
    def find_lvl1_region_plasmids(self, region_identity: str, *, min_material_state: MaterialState = MaterialState.PLANNED) -> list[IndexedPlasmid]: ...
    def find_backbone(self, *, fusion_sites: tuple[str, ...] | None = None, antibiotic: str | None = None, stage: BuildStage | None = None) -> IndexedBackbone | None: ...
    def find_restriction_enzyme(self, name: str) -> IndexedReagent | None: ...
    def find_ligase(self, preferred: str | None = None) -> IndexedReagent | None: ...
    def add_generated_product(self, product: IndexedPlasmid) -> None: ...
```

Inventory builds indexes eagerly and updates incrementally when generated products are added.

## Compatibility selection

`CompatibilitySelector` answers which valid route to use. Inventory should not own route-ranking policy.

Default ranking:

1. Respect request constraints.
2. Respect global selection options.
3. Prefer fewer new build products required.
4. Prefer existing collection material over generated/planned material.
5. Prefer higher material state.
6. Prefer exact antibiotic/fusion-site match.
7. Prefer simpler material routes.
8. Tie-break by stable SBOL identity.

Selection overrides live in both `BuildOptions.selection` and `BuildRequest.constraints`. Request constraints win over global options.

## Planning flows

### Design classification

`FullBuildPlanner` should classify designs into initial queues:

```text
ModuleDefinition -> assembly_lvl2
CombinatorialDerivation -> expand into assembly_lvl1 variant requests
ComponentDefinition with >1 component -> assembly_lvl1
ComponentDefinition with <=1 component and supported role -> domestication
ComponentDefinition with <=1 component and unsupported role -> unsupported
```

### Combinatorial expansion

- Expand valid concrete variants into level-1 requests.
- Validate each variant against level-1 cardinality.
- Skip invalid variants with structured warnings.
- Fail only if no valid variants remain.
- Default cap: `max_variants=256` unless `allow_large_expansion=True`.

## Execution flow

Use a bounded worklist/fixed-point loop:

```python
for iteration in range(options.execution.max_iterations):
    progress = False

    lvl2_results = run_buildable_lvl2_requests()
    progress |= index_products(lvl2_results)
    promote_missing_engineered_regions_to_lvl1(lvl2_results)

    lvl1_results = run_buildable_lvl1_requests()
    progress |= index_products(lvl1_results)
    promote_missing_parts_to_domestication(lvl1_results)

    domestication_results = run_buildable_domestication_requests()
    progress |= index_products(domestication_results)

    chain_transformation_and_plating_for_new_products()

    if all_requests_resolved():
        break
    if not progress:
        break
```

Safeguards:

- `max_iterations = 5` by default.
- Track `seen_products`, `seen_missing_inputs`, and `seen_requests`.
- Transform/plate each unique product only once.
- Raise unexpected implementation errors by default unless `continue_on_error=True`.

## Stage responsibilities

### Domestication stage

Responsibilities:

- Validate supported part role.
- Find required domestication backbone.
- Find BsaI and ligase reagents or return missing inputs.
- Propose internal BsaI sequence edits.
- Require approval in protocol/execution mode before using edited sequence.
- Create domesticated plasmid as primary product.
- Record insert and sequence-edit provenance as artifacts.

Primary product: domesticated plasmid.

### Assembly level 1 stage

Responsibilities:

- Resolve concrete level-1 design request.
- Extract exactly one promoter, one RBS, one CDS, one terminator.
- Use SBOL order if unambiguous.
- Warn if SBOL order differs from promoter/RBS/CDS/terminator.
- Use canonical order if SBOL order is ambiguous.
- Search candidate part plasmids and backbones.
- Select route minimizing new domestications.
- Return products or missing parts.
- Index products by plasmid identity and source engineered-region/design identity.

### Assembly level 2 stage

Responsibilities:

- Resolve `ModuleDefinition` with engineered-region components.
- Use `region_order` constraint if provided.
- If order absent and region count <= 4, enumerate candidate orders.
- If no full route exists, choose route requiring fewest new level-1 plasmids.
- Return selected route plus top 3 rejected alternatives when detailed reporting is enabled.
- Return missing engineered regions as level-1 requests.

### Transformation stage

Responsibilities:

- Consume generated plasmids.
- Create SBOL transformation records.
- Produce PUDU-compatible transformation JSON.
- Produce transformed strain records/products for plating.

### Plating stage

Responsibilities:

- Consume transformed strain outputs.
- Produce deterministic well mapping.
- Return plate map dictionary as main result.
- Optionally write CSV mapping with strain implementation URIs and dilution metadata.
- Produce PUDU-compatible plating JSON.
- No SBOL output is required for plating v1.

## SBOL assembly service

Port the current working `Assembly` behavior mostly intact into `sbol/assembly.py`, behind a cleaner service interface. Refactor internals only after tests protect the new contract.

```python
@dataclass
class AssemblyJob:
    stage: BuildStage
    product_identity: str
    product_display_id: str
    part_plasmids: list[IndexedPlasmid]
    backbone: IndexedBackbone
    restriction_enzyme: IndexedReagent
    ligase: IndexedReagent
    source_document: sbol2.Document
    target_document: sbol2.Document

@dataclass
class AssemblySbolResult:
    products: list[IndexedPlasmid]
    stage_document: sbol2.Document
    activity_identity: str
    logs: list[str]
```

## Adapter boundaries

Adapters translate BuildCompiler outputs into external inputs.

- Assembly PUDU JSON uses `Product`, `Backbone`, `PartsList`, and `Restriction Enzyme`.
- Transformation PUDU JSON uses `Strain`, `Chassis`, and `Plasmids`.
- Plating PUDU JSON uses `bacterium_locations` plus advanced parameters.

Compiler-only mode always creates in-memory JSON intermediates. File writing, manual Markdown, OT-2 scripts, and simulation are optional.

`simulate=True` is required for Opentrons simulation. Simulation is never default.

## Reporting

### BuildSummary

Always generated.

```python
@dataclass
class BuildSummary:
    status: BuildStatus
    final_product_count: int
    missing_input_count: int
    required_approval_count: int
    warning_count: int

    def to_dict(self) -> dict: ...
    def to_json(self) -> str: ...
    def to_markdown(self) -> str: ...
```

### BuildReport

Generated only when `include_detailed_report=True`.

```python
@dataclass
class BuildReport:
    status: BuildStatus
    executive_summary: str
    stage_sections: list[StageReportSection]
    selected_routes: list[RouteReport]
    rejected_alternatives: list[RouteReport]
    missing_inputs: list[MissingInputReport]
    required_approvals: list[ApprovalReport]
    warnings: list[WarningReport]
    next_actions: list[RecommendedAction]
    dependency_chain: list[DependencyChainStep]
    graph_summary: dict
```

`next_actions` tells the user what to do now. `dependency_chain` explains the path to final success.

## Operational concerns

### Configuration

- Keep defaults safe and compiler-only.
- Put broad options in focused dataclasses.
- Make network pull behavior explicit through `PullPolicy`.
- Make approvals run-scoped by default.

### Observability

- Replace `print` calls with `BuildLogger`.
- Include per-stage logs in `StageResult`.
- Include candidate route scoring in detailed reports.

### Security and safety

- Do not silently mutate sequences.
- Do not silently assume reagent purchases.
- Do not silently expand very large combinatorial designs.
- Do not silently perform large level-2 order searches.
- Do not run robot simulations as side effects.

### Testing

Core tests should run offline where possible. SynBioHub network access should be isolated behind integration tests or explicitly marked tests.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Clean rewrite becomes too large | Use milestone sequence and require passing tests at each layer. |
| SBOL object identity bugs | Keep canonical identity-based domain contracts and centralize lookup in `SbolResolver`. |
| Route optimizer complexity grows | Start with explicit scoring dataclasses and bounded search limits. |
| Current working level-1 assembly regresses | Port mostly intact first and protect with SBOL fixture tests before internal cleanup. |
| Optional PUDU/Opentrons dependencies destabilize CI | Keep automation tests optional/manual. |
| Sequence edits are unsafe | Require approval in execution/protocol mode and record provenance. |
| Reports become too verbose | Always generate lightweight summary; detailed report is opt-in. |
