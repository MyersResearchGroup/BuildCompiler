# Protocol equivalence acceptance

These tests compare the independent PUDU reference with both BuildCompiler OT-2 backends. All three run through the real Protocol Engine simulator using `opentrons analyze --check`. The original Python SDK comparisons through `opentrons.simulate.simulate` also remain in place. Unknown trace values and simulator failures fail the run.

Engine comparisons preserve command order, all execution parameters, resource and liquid definitions, loaded labware geometry, resolved positions, temperature programs and tip handling. Generated resource IDs are replaced by stable identifiers, equivalent top/bottom well offsets are normalized, and floating-point coordinates are rounded to nine decimal places. Informational comments and result bookkeeping such as timestamps, task IDs and module serial numbers are excluded. Physical results such as tip geometry, movement positions and liquid volumes are retained. Traces are written to each test's temporary directory.

Use Python 3.10 and the reference revision recorded in [pudu_reference.json](pudu_reference.json):

```bash
python -m pip install -e '.[test,automation]'
PUDU_REPOSITORY=../PUDU BUILDCOMPILER_REQUIRE_EQUIVALENCE=1 \
    python -m pytest tests/automation -q --basetemp=/tmp/buildcompiler-equivalence
```

The fixture verifies the source hashes. `BUILDCOMPILER_REQUIRE_EQUIVALENCE=1` makes missing dependencies or a missing reference checkout fail instead of skip. CI checks out the pinned reference, runs this command, and uploads the traces. Normal core tests require neither PUDU nor Opentrons.

Coverage includes assembly source ordering, replicates, offsets, rates, water testing and rack replacement; transformation source-location replicates, multiple plasmids, interleaved chassis, independent cell/media tube boundaries, both pipettes, offsets and thermal behavior; plating dilution counts, replicates, two agar plates, offsets and changing conical-source heights. A connected workflow checks assembly → transformation → plating using each implementation's own handoffs and verifies native sample lineage. Negative controls change flow rates, positions, tip wells, temperatures and module generations to establish that the engine comparator detects behavioral differences. An invalid-volume control must fail analysis.

PUDU forces transformation into water-testing mode during ordinary Python simulation. JSON protocols retain the complete execution program. For every engine comparison, the Python entrypoints override only `ProtocolContext.is_simulating` to exercise that same temperature path. Explicit water testing still removes temperatures from all three implementations. The original SDK comparisons separately cover ordinary simulation and the forced thermal path.

A separate native Python/JSON comparison checks fractional refill boundaries. PUDU's reagent-tube counter rejects that fractional input, so this extra case establishes equivalence to the Python SDK rather than claiming three-way reference coverage.

Generated protocols do not write files. Their expected handoffs are compiler artifacts compared against PUDU's simulation-generated JSON, and the two native bundles must have identical plans, manifests and handoffs. This verifies the covered simulator behavior, not physical hardware or experimental outcomes.
