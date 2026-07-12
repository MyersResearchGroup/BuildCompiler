Transformation and PUDU Protocol Chain
======================================

Use case
--------

You have run level-1 assembly and want to:

* transform the assembled product into a chassis strain,
* generate PUDU-compatible transformation JSON,
* generate PUDU assembly, transformation, and plating protocols, and
* simulate the full OT-2 handoff chain.

Notebook
--------

The full executable example lives in:

.. code-block:: text

   notebooks/buildcompiler_transformation_quickstart.ipynb

It produces artifacts in:

.. code-block:: text

   notebooks/results/buildcompiler_transformation_quickstart/

BuildCompiler transformation
----------------------------

After running ``assembly_lvl1``, pass the structured assembly products directly
to ``BuildCompiler.transformation``:

.. code-block:: python

   transformation_result = compiler.transformation(
       assembly_products,
       chassis_name="E_coli_DH5alpha",
       transformation_doc=assembly_doc,
   )

   transformation_spec = transformations_to_pudu_json(
       strain_identities=[
           artifact["transformed_strain_module"]
           for artifact in transformation_result["sbol_artifacts"]
       ],
       chassis_identities=["https://sbolcanvas.org/DH5alpha/1"],
       plasmid_sets=[
           [product.plasmid_definition.identity]
           for product in assembly_products
       ],
   )

PUDU transformation spec:

.. code-block:: json

   [
     {
       "Strain": "http://buildcompiler.org/E_coli_DH5alpha_with_standard_GFP_transformation_lvl1/1",
       "Chassis": "https://sbolcanvas.org/DH5alpha/1",
       "Plasmids": [
         "http://buildcompiler.org/standard_GFP_transformation_lvl1/1"
       ]
     }
   ]

PUDU protocol generation
------------------------

PUDU's documented handoff is:

.. code-block:: text

   assembly_input.json
      -> opentrons_simulate assembly_protocol.py
      -> transformation_input.json
      -> opentrons_simulate transformation_protocol.py
      -> plating_input.json
      -> opentrons_simulate plating_protocol.py
      -> plating_layout.json / plating_layout.xlsx

The notebook uses PUDU's Python API:

.. code-block:: python

   from pudu.generate_protocol import detect_protocol_type, generate_protocol

   assembly_protocol = generate_protocol(
       protocol_data=assembly_pudu,
       protocol_type="assembly",
       assembly_subtype="SBOL",
   )

   transformation_protocol = generate_protocol(
       protocol_data=transformation_spec,
       protocol_type="transformation",
       plasmid_locations=plasmid_locations,
   )

   plating_protocol = generate_protocol(
       protocol_data=plating_input,
       protocol_type="plating",
   )

The CLI equivalent is:

.. code-block:: bash

   python -m pudu.generate_protocol assembly_input.json -o assembly_protocol.py --protocol-type assembly
   opentrons_simulate assembly_protocol.py

   python -m pudu.generate_protocol transformation_spec.json -o transformation_protocol.py --protocol-type transformation --plasmid-locations transformation_input.json
   opentrons_simulate transformation_protocol.py

   python -m pudu.generate_protocol plating_input.json -o plating_protocol.py --protocol-type plating
   opentrons_simulate plating_protocol.py

Generated files
---------------

The validated notebook run generated:

* ``pudu_assembly_protocol.py``
* ``transformation_input.json``
* ``pudu_transformation_protocol.py``
* ``plating_input.json``
* ``pudu_plating_protocol.py``
* ``plating_layout.json``
* ``plating_layout.xlsx``

The final plating input shape matches PUDU:

.. code-block:: json

   {
     "bacterium_locations": {
       "A1": [
         "E_coli_DH5alpha_with_standard_GFP_transformation_lvl1",
         "Competent_Cell_DH5alpha",
         "standard_GFP_transformation_lvl1",
         "Media_1"
       ]
     }
   }
