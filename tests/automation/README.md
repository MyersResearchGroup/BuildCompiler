# Protocol equivalence acceptance

These tests run the independent PUDU reference and BuildCompiler's generated standalone Python through `opentrons.simulate.simulate`. They compare ordered structured robot commands, resource and liquid definitions, temperature-program arguments, touch-tip parameters, and JSON handoffs. Only informational `comment` commands are excluded. Unknown trace values and simulator failures fail the run.

Use Python 3.10 and the reference revision recorded in [pudu_reference.json](pudu_reference.json):

```bash
python -m pip install -e '.[test,simulation]'
PUDU_REPOSITORY=../PUDU BUILDCOMPILER_REQUIRE_EQUIVALENCE=1 \
    python -m pytest tests/automation -q --basetemp=/tmp/buildcompiler-equivalence
```

The fixture verifies the source hashes. `BUILDCOMPILER_REQUIRE_EQUIVALENCE=1` makes missing dependencies or a missing reference checkout fail instead of skip. CI checks out the pinned reference, runs this command, and uploads the traces. Normal core tests require neither PUDU nor Opentrons.

Coverage includes assembly source ordering, replicates, offsets, rates, water testing and rack replacement; transformation source-location replicates, multiple plasmids, interleaved chassis, independent cell/media tube boundaries, both pipettes, offsets and thermal behavior; plating dilution counts, replicates, two agar plates, offsets and changing conical-source heights. A connected workflow checks assembly → transformation → plating using each implementation's own handoffs and verifies native sample lineage. A changed-flow negative control establishes that the comparator detects a behavioral difference.

PUDU forces transformation into water-testing mode during simulation. Two additional transformation cases override only `ProtocolContext.is_simulating` in both entrypoints to exercise the ordinary temperature-program path and explicit water-testing override through the real simulator. These are separate from normal simulation parity.

The generated scripts do not write files. Their expected handoffs are compiler artifacts compared against PUDU's simulation-generated JSON. This verifies the covered simulator behavior, not physical hardware or experimental outcomes.
