# BuildCompiler Agent Handoff Log

Last updated: 2026-07-11

This log captures the recent BuildCompiler work so future agents can continue
without rediscovering the same repository and PUDU context.

## Repository Mental Model

BuildCompiler is a workflow orchestrator. Keep stages independently callable:

- `index_collections`
- `domestication`
- `assembly_lvl1`
- `assembly_lvl2`
- `transformation`
- `plating`
- `full_build`

Stage contracts should stay explicit:

- Inputs: SBOL objects/documents or JSON payloads.
- Outputs: SBOL, JSON, and protocol files.
- Avoid hidden side effects except explicitly named output files.
- Prefer deterministic JSON ordering and deterministic generated artifacts.

## Environment

Primary tested environment:

```bash
/Users/gonzalovidal/opt/anaconda3/bin/conda run -n GLLDB_py310 python ...
```

Useful commands:

```bash
/Users/gonzalovidal/opt/anaconda3/bin/conda run -n GLLDB_py310 python -m pytest tests/unit/adapters/pudu/test_transformation_json.py tests/unit/adapters/pudu/test_plating_json.py tests/test_buildcompiler_transformation.py
```

`opentrons_simulate` is available inside `GLLDB_py310`:

```bash
/Users/gonzalovidal/opt/anaconda3/bin/conda run -n GLLDB_py310 which opentrons_simulate
```

PUDU local source tree used for integration:

```text
/Users/gonzalovidal/Documents/GitHub/PUDU
```

When using PUDU from notebooks/scripts without installing it, prepend:

```python
sys.path.insert(0, "/Users/gonzalovidal/Documents/GitHub/PUDU/src")
```

## Recent BuildCompiler Changes

### Transformation input normalization

File:

- `src/buildcompiler/buildcompiler.py`

Added `_normalize_transformation_inputs()` so `BuildCompiler.transformation()`
accepts:

- BuildCompiler `Plasmid` objects produced by `assembly_lvl1`/`assembly_lvl2`.
- Raw `sbol2.ComponentDefinition` plasmids.
- Dict payloads with `plasmid` or `plasmid_definition`.

Reason: the active `BuildCompiler.transformation()` method referenced this
missing helper and failed when called with level-1 assembly products.

Regression test:

- `tests/test_buildcompiler_transformation.py::test_transformation_accepts_lvl1_assembly_products`

### PUDU transformation adapter

Files:

- `src/buildcompiler/adapters/pudu/transformation_json.py`
- `src/buildcompiler/adapters/pudu/__init__.py`
- `tests/unit/adapters/pudu/test_transformation_json.py`

Confirmed PUDU transformation spec shape:

```json
[
  {
    "Strain": "https://SBOL2Build.org/composite_strain_1/1",
    "Chassis": "https://sbolcanvas.org/DH5alpha/1",
    "Plasmids": ["https://SBOL2Build.org/composite_plasmid_1/1"]
  }
]
```

Added `plasmid_locations_to_pudu_json()` for PUDU's assembly-output location map:

```json
{
  "https://SBOL2Build.org/composite_plasmid_1/1": ["A1"]
}
```

This map is consumed by PUDU transformation protocol generation as
`--plasmid-locations transformation_input.json`.

Note: the notebook now prefers the location map produced by simulating PUDU's
assembly protocol, because that is the real handoff in the PUDU workflow.

### PUDU plating adapter

Files:

- `src/buildcompiler/adapters/pudu/plating_json.py`
- `tests/unit/adapters/pudu/test_plating_json.py`

Updated `plating_to_pudu_json()` to match PUDU directly. PUDU expects
thermocycler well names as keys:

```json
{
  "bacterium_locations": {
    "A1": [
      "composite_strain_1",
      "Competent_Cell_DH5alpha",
      "composite_plasmid_1",
      "Media_1"
    ]
  }
}
```

Removed the old nested `advanced_parameters` wrapper from the adapter output.
Optional advanced parameters now pass through as top-level PUDU parameters.

## Notebook Added

New notebook:

```text
notebooks/buildcompiler_transformation_quickstart.ipynb
```

It demonstrates the full offline/PUDU chain:

1. Load local SBOL collections:
   - `tests/test_files/CIDARMoCloParts_collection.xml`
   - `tests/test_files/CIDARMoCloPlasmidsKit_collection.xml`
   - `tests/test_files/Enzyme_Implementations_collection.xml`
   - `tests/test_files/impl_test_collection.xml`
2. Load `tests/test_files/abstract_design.xml`.
3. Run BuildCompiler `assembly_lvl1`.
4. Run BuildCompiler `transformation`.
5. Write BuildCompiler SBOL and JSON artifacts.
6. Generate PUDU assembly protocol.
7. Run `opentrons_simulate pudu_assembly_protocol.py`.
8. Use generated `transformation_input.json`.
9. Generate PUDU transformation protocol.
10. Run `opentrons_simulate pudu_transformation_protocol.py`.
11. Use generated `plating_input.json`.
12. Generate PUDU plating protocol.
13. Run `opentrons_simulate pudu_plating_protocol.py`.
14. Produce final `plating_layout.json` and `plating_layout.xlsx`.

Important implementation detail: SBOL files are written with
`Document.writeString()` and `Path.write_text()` rather than `Document.write()`
to avoid PySBOL2's online validator in offline notebook runs.

## Generated Notebook Artifacts

Directory:

```text
notebooks/results/buildcompiler_transformation_quickstart/
```

Current generated files include:

- `assembly_lvl1_pudu_input.json`
- `transformation_lvl1_products.xml`
- `transformation_products.xml`
- `transformation_summary.json`
- `transformation_lvl1_pudu_input.json`
- `pudu_assembly_protocol.py`
- `pudu_assembly_protocol.simulate.log`
- `transformation_input.json`
- `pudu_transformation_protocol.py`
- `pudu_transformation_protocol.simulate.log`
- `plating_input.json`
- `pudu_plating_protocol.py`
- `pudu_plating_protocol.simulate.log`
- `plating_layout.json`
- `plating_layout.xlsx`
- `Loop Assembly.xlsx`

The simulation logs showed the expected handoff:

- Assembly simulation generated `transformation_input.json`.
- Transformation simulation generated `plating_input.json`.
- Plating simulation generated `plating_layout.json` and `plating_layout.xlsx`.

## PUDU Reference Points

Local files inspected:

- `/Users/gonzalovidal/Documents/GitHub/PUDU/docs/guide/workflow.rst`
- `/Users/gonzalovidal/Documents/GitHub/PUDU/docs/api/transformation.rst`
- `/Users/gonzalovidal/Documents/GitHub/PUDU/src/pudu/generate_protocol.py`
- `/Users/gonzalovidal/Documents/GitHub/PUDU/src/pudu/transformation.py`
- `/Users/gonzalovidal/Documents/GitHub/PUDU/src/pudu/plating.py`
- `/Users/gonzalovidal/Documents/GitHub/PUDU/workflow_example/transformation_spec.json`
- `/Users/gonzalovidal/Documents/GitHub/PUDU/workflow_example/transformation_input.json`
- `/Users/gonzalovidal/Documents/GitHub/PUDU/workflow_example/plating_input.json`

PUDU's documented flow:

```text
assembly_input.json
  -> pudu_assembly_protocol.py
  -> opentrons_simulate
  -> transformation_input.json
  -> pudu_transformation_protocol.py
  -> opentrons_simulate
  -> plating_input.json
  -> pudu_plating_protocol.py
  -> opentrons_simulate
  -> plating_layout.json / plating_layout.xlsx
```

PUDU Python API used in notebook:

```python
from pudu.generate_protocol import detect_protocol_type, generate_protocol
```

PUDU CLI equivalent:

```bash
python -m pudu.generate_protocol assembly_input.json -o assembly_protocol.py --protocol-type assembly
opentrons_simulate assembly_protocol.py

python -m pudu.generate_protocol transformation_spec.json -o transformation_protocol.py --protocol-type transformation --plasmid-locations transformation_input.json
opentrons_simulate transformation_protocol.py

python -m pudu.generate_protocol plating_input.json -o plating_protocol.py --protocol-type plating
opentrons_simulate plating_protocol.py
```

## Validation Performed

Notebook execution:

```bash
/Users/gonzalovidal/opt/anaconda3/bin/conda run -n GLLDB_py310 python -c "import json; ns={}; nb=json.load(open('notebooks/buildcompiler_transformation_quickstart.ipynb')); [exec(''.join(cell.get('source', [])), ns) for cell in nb['cells'] if cell.get('cell_type') == 'code']"
```

Adapter and regression tests:

```bash
/Users/gonzalovidal/opt/anaconda3/bin/conda run -n GLLDB_py310 python -m pytest tests/unit/adapters/pudu/test_transformation_json.py tests/unit/adapters/pudu/test_plating_json.py tests/test_buildcompiler_transformation.py
```

Last observed targeted results:

- PUDU transformation/plating adapter tests: passed.
- BuildCompiler transformation regression tests: passed.
- Full notebook simulation chain: passed.

## Current Worktree Notes

At the time this log was written, expected modified/untracked files included:

- `src/buildcompiler/adapters/pudu/__init__.py`
- `src/buildcompiler/adapters/pudu/transformation_json.py`
- `src/buildcompiler/adapters/pudu/plating_json.py`
- `src/buildcompiler/buildcompiler.py`
- `tests/test_buildcompiler_transformation.py`
- `tests/unit/adapters/pudu/test_transformation_json.py`
- `tests/unit/adapters/pudu/test_plating_json.py`
- `notebooks/buildcompiler_transformation_quickstart.ipynb`
- `notebooks/results/buildcompiler_transformation_quickstart/`
- `AGENTS_log.md`

Do not revert unrelated user changes. If these files differ from this log,
inspect before editing.

## Next Work Suggestions

- Add a dedicated notebook/test for full-build output feeding the same PUDU
  protocol chain.
- Decide whether generated notebook results should be committed or moved to an
  ignored artifact path.
- Consider a higher-level BuildCompiler helper that returns all PUDU artifacts
  for a stage chain without requiring notebook glue code.
- Add optional dependency documentation for PUDU and Opentrons simulation.
- Keep PUDU as optional unless the package is intentionally added as a dependency.
