# Testing guide

## Core (required) checks

Core CI is compiler-only and offline (except fixture-local SBOL files).

```bash
ruff check .
ruff format --check .
pytest tests/unit tests/stages tests/integration
```

Core tests must not require SynBioHub, PUDU, Opentrons, or SBOLInventory.

## Optional automation checks

```bash
python -m pip install -e '.[automation,test]'
pytest tests/automation
```

Automation tests are marked with `@pytest.mark.automation` and are manual/optional.

## Skip vs xfail guidance

- Use `skip` for intentionally manual checks (e.g., hardware simulation).
- Use `xfail` only for known core blockers and include explicit issue references.

## Fixtures

- `tests/fixtures/sbol/`: fixture-local SBOL files.
- `tests/fixtures/data/`: small deterministic JSON/data fixtures.
- Shared fixture helpers are in `tests/conftest.py`.
