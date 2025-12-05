# BuildPlanner
SBOL2Build is a Python library for assisting in the planning, documentation, and distribution of DNA assembly plans using the Synthetic Biology Open Language 2.3 data standard.

It was developed to support build functionality and workflows in [SynBioSuite](https://synbiosuite.org), based off the [SBOL Best Practices](https://github.com/SynBioDex/SBOL-examples/tree/main/SBOL/best-practices/BP011/).



![PyPI - Version](https://img.shields.io/pypi/v/sbol2build)
[![Documentation Status](https://readthedocs.org/projects/sbol2build/badge/?version=latest)](https://sbol2build.readthedocs.io/en/latest/?badge=latest)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/sbol2build)
![PyPI - License](https://img.shields.io/pypi/l/sbol2build)
![gh-action badge](https://github.com/MyersResearchGroup/sbol2build/workflows/Python%20package/badge.svg)

## Installing SBOL2Build: 
```pip install sbol2build```

## Documentation

 Please visit the documentation with API reference and tutorials at Read the Docs: [sbol2build.rtfd.io](https://sbol2build.readthedocs.io)

## Environment Setup

If you are interested in contributing to **BuildPlanner**, please set up your local development environment with the same tools used in CI and linting.

### 1. Install [uv](https://docs.astral.sh/uv/)

`uv` manages all Python dependencies (including dev tools) with a lockfile for reproducibility.

#### Linux/Bash
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
#### Mac OSX with Homebrew
```bash
brew install uv
```
### 2. Sync dependencies
```bash
uv sync --all-groups
```
This will create a virtual environment with the dependiencies. Activate using:
```bash
source .venv/bin/activate
```

### 3. Install pre-commit hooks
We use pre-commit to automatically run the Ruff linter before every commit.
Install and enable the hooks with:
```bash
uv run pre-commit install
```


#### Running tests:
`uv run python -m unittest discover -s tests`