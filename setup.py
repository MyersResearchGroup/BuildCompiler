"""Compatibility shim for editable installs with older pip/setuptools."""

from pathlib import Path

from setuptools import find_packages, setup


ROOT = Path(__file__).parent
README = ROOT / "README.md"


setup(
    name="synbio-buildcompiler",
    version="0.0.1a1",
    description=(
        "BuildCompiler is an open-source tool that bridges the Design and Build "
        "stages of the Synthetic Biology DBTL cycle"
    ),
    long_description=README.read_text(encoding="utf-8") if README.exists() else "",
    long_description_content_type="text/markdown",
    author="Gonzalo Vidal, Ryan Greer",
    author_email="gonzalo.vidalpena@colorado.edu",
    maintainer="Ryan Greer",
    maintainer_email="ryan.greer@colorado.edu",
    license="MIT",
    url="https://github.com/MyersResearchGroup/BuildCompiler",
    project_urls={
        "Bug Tracker": "https://github.com/MyersResearchGroup/BuildCompiler/issues",
        "Source": "https://github.com/MyersResearchGroup/BuildCompiler",
    },
    package_dir={"": "src"},
    packages=find_packages("src"),
    python_requires=">=3.10",
    install_requires=[
        "sbol2",
        "biopython",
        "pydna",
    ],
    extras_require={
        "test": [
            "pytest>=7,<9",
            "pytest-cov[all]",
        ],
        "dev": [
            "pytest>=7,<9",
            "pytest-cov[all]",
            "ruff>=0.14.0",
            "build>=1.2",
            "twine>=5.0",
        ],
        "automation": [
            "pudupy",
            "opentrons",
            "SBOLInventory @ "
            "git+https://github.com/DRAGGON-Lab/SBOLInventory.git ; "
            "python_version >= '3.10'",
        ],
    },
    keywords=["SBOL", "genetic", "automation", "build", "synthetic biology"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
    ],
)
