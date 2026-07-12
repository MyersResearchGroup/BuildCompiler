Offline Level-1 Assembly
========================

Use case
--------

You have an abstract level-1 SBOL design and local SBOL collections containing
the required part plasmids, backbone plasmids, and enzyme implementations. You
want BuildCompiler to produce:

* an assembled product SBOL document,
* a deterministic PUDU assembly input JSON file, and
* a list of route inputs used to build the plasmid.

Example
-------

.. code-block:: python

   from pathlib import Path

   import sbol2

   from buildcompiler.abstract_translator import extract_toplevel_definition
   from buildcompiler.adapters.pudu import write_assembly_pudu_input_json
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

   design_doc = sbol2.Document()
   design_doc.read(str(test_files / "abstract_design.xml"))
   design = extract_toplevel_definition(design_doc)

   compiler = BuildCompiler.from_local_documents(
       collection_docs,
       design_doc=design_doc,
   )

   product_doc = sbol2.Document()
   routes, product_doc = compiler.assembly_lvl1(
       [design],
       final_doc=product_doc,
       product_name="offline_lvl1",
   )

   results = Path("results/offline_lvl1")
   results.mkdir(parents=True, exist_ok=True)
   (results / "offline_lvl1_products.xml").write_text(
       product_doc.writeString(),
       encoding="utf-8",
   )
   write_assembly_pudu_input_json(
       compiler.last_assembly_pudu_json,
       results / "offline_lvl1_pudu_input.json",
   )

The generated PUDU input has this shape:

.. code-block:: json

   [
     {
       "Product": "http://buildcompiler.org/offline_lvl1/1",
       "Backbone": "https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/DVK_AE/1",
       "PartsList": [
         "https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/pJ23100_AB/1",
         "https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/pB0034_BC/1",
         "https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/pE0040_CD/1",
         "https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/pB0015_DE/1"
       ],
       "Restriction Enzyme": "https://synbiohub.org/user/Gon/Enzyme_Implementations/BsaI/1"
     }
   ]

Notes
-----

``compiler.last_assembly_pudu_json`` is populated by the assembly stage from
the route selected by BuildCompiler. It does not scrape the generated SBOL
document, so it retains the product plasmid, backbone plasmid, part plasmids,
and enzyme implementation used by the route.
