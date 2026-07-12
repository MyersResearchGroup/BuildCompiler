"""Sphinx configuration for BuildCompiler documentation."""

from __future__ import annotations

import os
import sys
from importlib import metadata

sys.path.insert(0, os.path.abspath("../src"))

project = "BuildCompiler"
copyright = "2026, BuildCompiler contributors"
author = "BuildCompiler contributors"

try:
    release = metadata.version("synbio-buildcompiler")
except metadata.PackageNotFoundError:
    release = "0.0.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

autosummary_generate = True
autodoc_typehints = "description"
autodoc_member_order = "bysource"

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_title = "BuildCompiler"
html_static_path = ["_static"]
html_logo = "../images/buildcompiler_logo.png"

html_theme_options = {
    "source_repository": "https://github.com/MyersResearchGroup/BuildCompiler/",
    "source_branch": "main",
    "source_directory": "docs/",
    "light_css_variables": {},
    "dark_css_variables": {},
}
