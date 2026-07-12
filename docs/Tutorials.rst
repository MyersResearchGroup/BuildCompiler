Tutorials
======================================
Let's get started with creating DNA assembly plans. First we will demonstrate a workflow using plasmid files from `SBOLCanvas <https://sbolcanvas.org/>`_:

.. code:: ipython3

    import sbol2build as s2b
    import sbol2

First, read your plasmid SBOL files into documents.

.. code:: ipython3
    
    promoter = sbol2.Document()
    promoter.read('pro_in_bb.xml')

    rbs = sbol2.Document()
    rbs.read('rbs_in_bb.xml')

    cds = sbol2.Document()
    cds.read('cds_in_bb.xml')

    terminator = sbol2.Document()
    terminator.read('terminator_in_bb.xml')

    backbone = sbol2.Document()
    backbone.read('backbone.xml')

Create golden gate assembly plan object with all the parts, the acceptor backbone, and restriction enzyme.

.. code:: ipython3

    assembly_doc = sbol2.Document()
    
    assembly_plan = s2b.golden_gate_assembly_plan('tutorial_assembly_plan', [promoter, rbs, cds, terminator], backbone, 'BsaI', assembly_doc)
    
    composites = assembly_plan.run()

Full build level-2 PUDU artifact package
----------------------------------------

The legacy artifact-producing compiler can run a level-2 design and package all
generated SBOL, JSON, and PUDU protocol inputs into a single zip file. If the
level-2 design is missing level-1 region inputs, ``full_build`` attempts level-1
assembly, falls back to domestication for missing parts, then retries the
downstream assemblies.

.. code:: python

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
        results_dir="results/full_build_lvl2_pudu",
        overwrite=True,
    )

    print(result["zip_path"])

The zip archive includes ``full_build_manifest.json`` plus PUDU assembly,
transformation, and plating inputs/scripts such as
``assembly_lvl2_pudu_assembly_input.json``,
``assembly_lvl1_pudu_assembly_input.json``,
``domestication_pudu_assembly_input.json``,
``pudu_transformation_protocol.py``, and ``pudu_plating_protocol.py``.
