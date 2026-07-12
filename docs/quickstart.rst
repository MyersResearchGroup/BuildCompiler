Quickstart
==========

This quickstart uses only files that ship with the repository. It does not
require SynBioHub network access.

Install the package in editable mode:

.. code-block:: bash

   python -m pip install -e ".[test]"

Load the local fixture collections:

.. code-block:: python

   from pathlib import Path

   import sbol2

   from buildcompiler.abstract_translator import extract_toplevel_definition
   from buildcompiler.buildcompiler import BuildCompiler

   repo = Path.cwd()
   test_files = repo / "tests" / "test_files"

   collection_paths = [
       test_files / "CIDARMoCloParts_collection.xml",
       test_files / "CIDARMoCloPlasmidsKit_collection.xml",
       test_files / "Enzyme_Implementations_collection.xml",
       test_files / "impl_test_collection.xml",
   ]

   collection_docs = []
   for path in collection_paths:
       doc = sbol2.Document()
       doc.read(str(path))
       collection_docs.append(doc)

   design_doc = sbol2.Document()
   design_doc.read(str(test_files / "abstract_design.xml"))
   design = extract_toplevel_definition(design_doc)

   compiler = BuildCompiler.from_local_documents(
       collection_docs,
       design_doc=design_doc,
   )

Run level-1 assembly:

.. code-block:: python

   product_doc = sbol2.Document()
   assembly_routes, product_doc = compiler.assembly_lvl1(
       [design],
       final_doc=product_doc,
       product_name="quickstart_lvl1",
   )

   products = assembly_routes[design.identity]
   print([product.plasmid_definition.displayId for product in products])

Write SBOL and PUDU JSON artifacts:

.. code-block:: python

   import json

   from buildcompiler.adapters.pudu import write_assembly_pudu_input_json

   results = repo / "docs_results" / "quickstart"
   results.mkdir(parents=True, exist_ok=True)

   (results / "quickstart_lvl1_products.xml").write_text(
       product_doc.writeString(),
       encoding="utf-8",
   )
   write_assembly_pudu_input_json(
       compiler.last_assembly_pudu_json,
       results / "quickstart_lvl1_pudu_input.json",
   )

``Document.writeString()`` is used in offline examples because
``sbol2.Document.write()`` may attempt online validation.
