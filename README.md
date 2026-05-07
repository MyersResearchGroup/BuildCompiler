# BuildCompiler

BuildCompiler is a Python compiler pipeline for synthetic biology build planning. It takes abstract SBOL designs and indexed biological inventory, then produces an executable build plan across domestication, MoClo assembly level 1, MoClo assembly level 2, transformation, and plating.

This repository is being refactored around a clean architecture. The existing codebase is useful as working evidence, especially the level-1 assembly path and SBOL digestion/ligation behavior, but the new implementation should not preserve old APIs, old import paths, or legacy module boundaries except the root package name `buildcompiler`.

## Why this exists

Designing a genetic construct is easier than building it in the lab. BuildCompiler should bridge that gap by compiling:

```text
abstract SBOL design + inventory -> build plan -> SBOL build artifacts -> PUDU JSON -> optional manual/OT-2 protocols
```

The compiler should answer:

- Can this design be built from current inventory?
- Which plasmids, backbones, and reagents are required?
- Which missing engineered regions need level-1 assembly?
- Which missing promoter/RBS/CDS/terminator parts need domestication?
- Which route minimizes new build work?
- Which transformations and plating layouts follow from successful products?
- What actions should a user take next when a build is blocked?

## Core capabilities for v1

- Classify SBOL abstract designs into level-2, level-1, domestication, or unsupported work.
- Plan and execute a bounded full-build dependency loop.
- Support partial success: build what can be built, report what is missing, and retry after generated products are indexed.
- Optimize level-2 routes by searching feasible engineered-region orders and minimizing new level-1 plasmids.
- Optimize level-1 routes by minimizing new domestications.
- Produce cumulative and per-stage SBOL build artifacts.
- Produce in-memory PUDU-compatible JSON intermediates in compiler-only mode.
- Chain successful assembly/domestication products to transformation and plating, deduplicated by product identity.
- Return structured statuses, missing inputs, required approvals, warnings, summaries, and optional detailed reports.
- Keep PUDU protocol generation and Opentrons simulation optional.

## Non-goals for v1

- Do not preserve legacy APIs or compatibility wrappers.
- Do not implement DNA extraction as a real stage; reserve `extracted` as a future material state.
- Do not run PUDU or Opentrons simulation by default.
- Do not make the build graph the scheduler in v1; it is reporting-only.
- Do not support variable-length level-1 constructs in v1.
- Do not silently approve sequence edits, reagent purchase, large combinatorial expansion, or large level-2 order search.

## Architecture at a glance

BuildCompiler should be organized as a compiler pipeline:

```text
api -> planning -> execution -> stages -> sbol/inventory/adapters -> reporting
```

Recommended package layout:

```text
src/buildcompiler/
  __init__.py

  api/
    __init__.py
    compiler.py
    options.py

  domain/
    __init__.py
    build_request.py
    build_result.py
    missing_input.py
    material_state.py
    plasmid.py
    reagent.py
    design.py
    approvals.py
    warnings.py

  planning/
    __init__.py
    classifier.py
    combinatorial.py
    full_build_planner.py
    validation.py

  execution/
    __init__.py
    context.py
    full_build_executor.py
    worklist.py
    stage_runner.py
    indexing.py

  stages/
    __init__.py
    domestication.py
    assembly_lvl1.py
    assembly_lvl2.py
    transformation.py
    plating.py

  sbol/
    __init__.py
    assembly.py
    domestication.py
    transformation.py
    documents.py
    identities.py
    resolver.py
    validation.py
    constants.py

  inventory/
    __init__.py
    synbiohub.py
    collection_indexer.py
    plasmid_index.py
    backbone_index.py
    reagent_index.py
    product_index.py
    compatibility.py
    selector.py

  adapters/
    __init__.py
    pudu/
      __init__.py
      assembly_json.py
      transformation_json.py
      plating_json.py
      protocol_generation.py
    opentrons/
      __init__.py
      simulation.py

  reporting/
    __init__.py
    build_graph.py
    summaries.py
    reports.py
    serialization.py

  errors.py
  logging.py
```

## Public API target

Keep the import root `buildcompiler`.

Primary usage should be stateful and object-based:

```python
from buildcompiler.api import BuildCompiler

compiler = BuildCompiler.from_synbiohub(
    collections=collections,
    sbh_registry=sbh_registry,
    auth_token=auth_token,
    sbol_doc=sbol_doc,
)

plan = compiler.plan(abstract_designs)
result = compiler.execute(plan)
```


Authenticated and anonymous repository access are both supported:

```python
compiler = BuildCompiler.from_synbiohub(
    collections=["https://synbiohub.org/public/igem/igem_collection/1"],
    repository_url="https://synbiohub.org",
    auth_token="<token>",
)

compiler = BuildCompiler.from_synbiohub(
    repository_url="https://synbiohub.org",
    email="user@example.org",
    password="<password>",
)

compiler = BuildCompiler.from_synbiohub(
    repository_url="https://synbiohub.org",
)
```

A convenience wrapper may exist:

```python
from buildcompiler.api import full_build

result = full_build(
    abstract_designs=abstract_designs,
    collections=collections,
    sbh_registry=sbh_registry,
    auth_token=auth_token,
    sbol_doc=sbol_doc,
)
```

`BuildCompiler.__init__` should stay lightweight and dependency-injected. Automatic SynBioHub collection indexing belongs in `BuildCompiler.from_synbiohub(...)`.

## Local development

Recommended local workflow:

```bash
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

If `uv` is not available, use a normal virtual environment and install editable dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e '.[test]'
python -m pip install ruff
ruff check .
ruff format --check .
pytest
```

Automation-specific tests should be optional:

```bash
python -m pip install -e '.[automation,test]'
pytest tests/automation
```

## Container workflow

A Docker Compose workflow is recommended for reliable Codex and contributor development, but it does not need to block the first implementation PR.

Target commands after Docker support exists:

```bash
docker compose build
docker compose run --rm app ruff check .
docker compose run --rm app ruff format --check .
docker compose run --rm app pytest
```

Core CI should not require PUDU or Opentrons. Those dependencies are optional and should live behind optional test jobs or manual workflows.

## Testing and quality checks

Default CI should run:

```bash
ruff check .
ruff format --check .
pytest tests/unit tests/stages tests/integration
```

Testing priorities:

1. Domain dataclasses and status semantics.
2. Planning and design classification.
3. Inventory indexing and compatibility selection.
4. Level-1 and level-2 route optimizers.
5. Domestication sequence-edit approval behavior.
6. Full-build bounded retry loop with mocked stages.
7. SBOL assembly service port using existing fixtures.
8. Transformation and plating deduplication.
9. Summary/report/graph generation.
10. Optional PUDU/Opentrons adapter smoke tests.

## How ChatGPT and Codex should use these docs

- `PRODUCT.md` defines the product intent, v1 scope, and non-goals.
- `ARCHITECTURE.md` defines module boundaries and implementation contracts.
- `AGENT.md` defines how Codex should take tasks, report progress, and escalate decisions.
- `ADR-001.md` records the clean-architecture rewrite decision and its tradeoffs.

Codex should treat these files as the source of truth for implementation unless the user or ChatGPT explicitly revises them.
