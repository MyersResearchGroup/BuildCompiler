Full Build Workflows
====================

Use case
--------

You want BuildCompiler to resolve a higher-level design, trigger upstream
stages when material is missing, and package all generated build artifacts.

The legacy artifact-producing ``BuildCompiler.full_build`` path can produce
SBOL, JSON, PUDU inputs, PUDU protocol scripts, and a manifest.

Level-2 build example
---------------------

.. code-block:: python

   from pathlib import Path

   import sbol2

   from buildcompiler.buildcompiler import BuildCompiler

   test_files = Path("tests/test_files")
   collection_docs = []
   for filename in (
       "CIDARMoCloParts_collection.xml",
       "CIDARMoCloPlasmidsKit_collection.xml",
       "Enzyme_Implementations_collection.xml",
       "impl_test_collection.xml",
   ):
       doc = sbol2.Document()
       doc.read(str(test_files / filename))
       collection_docs.append(doc)

   lvl2_design_doc = sbol2.Document()
   lvl2_design_doc.read(str(test_files / "ExampleLvl2_design.xml"))

   compiler = BuildCompiler.from_local_documents(
       collection_docs,
       design_doc=lvl2_design_doc,
   )
   result = compiler.full_build(
       designs=lvl2_design_doc,
       results_dir="results/full_build_lvl2",
       overwrite=True,
   )

   print(result["zip_path"])

Expected artifacts
------------------

Depending on which inputs are already available, full build may emit:

* ``domestication_pudu_assembly_input.json``
* ``assembly_lvl1_pudu_assembly_input.json``
* ``assembly_lvl2_pudu_assembly_input.json``
* ``transformation_pudu_input.json``
* ``plating_pudu_input.json``
* ``pudu_transformation_protocol.py``
* ``pudu_plating_protocol.py``
* ``full_build_manifest.json``

Representative generated examples are stored under:

.. code-block:: text

   notebooks/results/full_build_workflow_examples/

Behavior
--------

The full-build planner/executor is intended to:

* use existing inventory when possible,
* trigger level-1 assembly when a level-2 design is missing a region plasmid,
* trigger domestication when level-1 assembly is missing a part plasmid,
* retry downstream stages after generated products are indexed, and
* report partial success or missing inputs instead of silently failing.
