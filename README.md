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

# BuildCompiler

BuildCompiler is an open-source framework that converts **abstract genetic designs** into **fully executable cloning workflows** using MoClo (Golden Gate) assembly.

It bridges the gap between *design* and *build* in the Design–Build–Test–Learn (DBTL) cycle by automatically generating:

- DNA assembly plans
- Lab automation protocols (Opentrons OT-2)
- Transformation workflows
- Plating protocols
- Step-by-step execution instructions

👉 Instead of manually planning cloning experiments, BuildCompiler **compiles them**.

---

## 🧬 What Problem Does It Solve?

Designing genetic constructs is easy.  
Building them in the lab is not.

BuildCompiler automates the transition from:

**SBOL design → DNA → cells on plates**

This reduces:
- Manual planning errors
- Protocol design time
- Lab-to-lab variability

---

## ⚙️ Core Capabilities

BuildCompiler provides a complete cloning workflow composed of:

### 1. Index Collections
Scans SBOL documents to build an internal index of available plasmids.

### 2. Domestication
Creates missing parts as linear DNA and generates protocols to insert them into plasmids.

### 3. Assembly Level 1 (Single Gene)
- Maps abstract parts → plasmids
- Builds a gene using MoClo
- Generates automation-ready protocols

### 4. Assembly Level 2 (Multi-Gene)
- Combines up to 4 genes into a construct
- Uses Level 1 products as inputs

### 5. Transformation
- Converts DNA into engineered strains
- Generates automated chemical transformation protocols

### 6. Plating
- Creates dilution series
- Generates plating protocols

#### Example: Generate plating protocol artifacts from transformation results

```python
from buildcompiler.buildcompiler import BuildCompiler

compiler = BuildCompiler(collections=[], sbh_registry="", auth_token="", sbol_doc=None)

transformation_results = {
    "thermocycler_wells": {
        "A1": "strain_001",
        "A2": "strain_002"
    }
}

advanced_params = {
    "target_colonies": 12,
    "spots_per_strain": 2
}

artifacts = compiler.plating(
    transformation_results=transformation_results,
    results_dir="plating_outputs",
    advanced_params=advanced_params,
    zip_name="plating_simulation.zip",
)

print(artifacts["simulation_zip"])  # plating_outputs/plating_simulation.zip
```

### 7. Full Build (Orchestrator)
Runs the entire workflow automatically:
- Detects missing parts
- Generates them if needed
- Executes all assembly steps
- Chains transformation and plating

---

## 🔄 Full Build Workflow

```text
SBOL Design
     ↓
Index Collections
     ↓
Domestication
     ↓
Transformation
     ↓
Plating
     ↓
DNA Extraction
     ↓
Assembly Level 1 (Missing parts added to Domestication)
     ↓
Transformation
     ↓
Plating
     ↓
DNA Extraction
     ↓
Assembly Level 2 (Missing parts added to Assembly Level 1)
     ↓
Transformation
     ↓
Plating
     ↓
Final Build Outputs
```

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
