Notebooks
=========

Notebook examples are kept in the repository so users can inspect and execute
real SBOL workflows.

Recommended starting points
---------------------------

``notebooks/buildcompiler_offline_quickstart.ipynb``
   Offline SBOL collection loading, level-1 assembly, level-2 assembly,
   domestication, and full-build examples.

``notebooks/buildcompiler_transformation_quickstart.ipynb``
   Offline level-1 assembly followed by BuildCompiler transformation and the
   complete PUDU assembly/transformation/plating simulation chain.

``notebooks/full_build_workflow_examples.ipynb``
   Full-build artifact packaging examples.

Notebook result directories
---------------------------

Generated outputs are stored under ``notebooks/results``. The most useful
directory for automation integration is:

.. code-block:: text

   notebooks/results/buildcompiler_transformation_quickstart/

It contains generated PUDU protocol scripts, simulator logs, intermediate JSON
handoff files, and the final plating layout.
