# Release checklist

- [ ] Core CI (`pytest tests/unit tests/stages tests/integration`) is green.
- [ ] `ruff check .` is green.
- [ ] `ruff format --check .` is green.
- [ ] Happy-path integration fixture passes (or has explicit xfail with blocking issue).
- [ ] Missing-lvl1-then-domestication integration fixture passes (or has explicit xfail with blocking issue).
- [ ] Optional automation tests are documented and kept manual.
- [ ] Core tests do not import optional automation dependencies.
- [ ] README testing commands remain accurate.
- [ ] Known upstream blockers are documented with issue references.
