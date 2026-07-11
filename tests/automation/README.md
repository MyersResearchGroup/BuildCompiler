# Automation test suite (optional/manual)

These tests are intentionally separated from core CI.

Run only when optional dependencies are installed:

```bash
python -m pip install -e '.[automation,test]'
pytest tests/automation
```
