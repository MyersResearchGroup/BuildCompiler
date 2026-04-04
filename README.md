# BuildCompiler
 BuildCompiler is an open-source tool that bridges the Design and Build stages of the Synthetic Biology DBTL cycle by compiling standardized genetic designs into executable DNA assembly, transformation, and plating workflows.

It supports build functionality in comand line and cloud workflows in [SynBioSuite](https://synbiosuite.org), based off the [SBOL Best Practices](https://github.com/SynBioDex/SBOL-examples/tree/main/SBOL/best-practices/BP011/).

<img src="https://github.com/MyersResearchGroup/BuildCompiler/blob/main/images/buildcompiler_logo.png#gh-light-mode-only" alt="BuildCompiler light logo" width="300"/>
<img src="https://github.com/MyersResearchGroup/BuildCompiler/blob/main/images/buildcompiler_logo.png#gh-dark-mode-only" alt="BuildCompiler night logo" width="300"/> 

![PyPI - Version](https://img.shields.io/pypi/v/sbol2build)
[![Documentation Status](https://readthedocs.org/projects/sbol2build/badge/?version=latest)](https://sbol2build.readthedocs.io/en/latest/?badge=latest)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/sbol2build)
![PyPI - License](https://img.shields.io/pypi/l/sbol2build)
![gh-action badge](https://github.com/MyersResearchGroup/sbol2build/workflows/Python%20package/badge.svg)

## Why this project exists

Synthetic biology design tools often stop at *design representation*. BuildCompiler closes the gap between:

1. **Design intent** in SBOL. SBOLCanvas, Cello, and LOICA support SBOL outputs.
2. **Part/backbone selection**. Load your lab inventory to be used by BuildCompiler 
3. **Assembly simulation**. Plasmids are digested to generate products by ligation. 
4. **Output artifacts**. Protocols, instructions and lab automation scripts to accelerate your workflows.

## Installing BuildCompiler: 
```pip install buildcompiler```

## Documentation

 Please visit the documentation with API reference and tutorials at Read the Docs: [sbol2build.rtfd.io](https://sbol2build.readthedocs.io)

## Environment Setup

If you are interested in contributing to **BuildCompiler**, please set up your local development environment with the same tools used in CI and linting.

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
