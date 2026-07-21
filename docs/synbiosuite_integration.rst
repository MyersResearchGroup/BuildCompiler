SynBioSuite integration
=======================

SynBioSuite should use only the clean API exported from
``buildcompiler.api``. The integration does not require PUDU or Opentrons.

Load token-authenticated collections
------------------------------------

The factory signature is:

.. code-block:: python

   BuildCompiler.from_synbiohub(
       *,
       collections: list[str] | None = None,
       sbh_registry: str | None = None,
       auth_token: str | None = None,
       sbol_doc: sbol2.Document | None = None,
       options: BuildOptions | None = None,
   ) -> BuildCompiler

Call it with a token, never a username or password:

.. code-block:: python

   from buildcompiler.api import BuildCompiler, BuildOptions

   compiler = BuildCompiler.from_synbiohub(
       collections=[
           "https://synbiohub.example/user/team/plasmids/plasmids_collection/1",
           "https://synbiohub.example/user/team/reagents/reagents_collection/1",
       ],
       sbh_registry="https://synbiohub.example",
       auth_token=request.headers["Authorization"].removeprefix("Bearer "),
       options=BuildOptions(),
   )
   plan = compiler.plan(abstract_designs)

The token exists only on a transient PartShop during download and is cleared
before the factory returns. The compiler retains the hydrated SBOL document,
normalized inventory, and local resolver. Authentication, network, missing
resource, and response failures are exposed as the typed ``SynBioHub*Error``
classes exported from ``buildcompiler.api``.

Versioned JSON DTOs
-------------------

Use these exact public calls at the HTTP boundary:

.. code-block:: python

   from buildcompiler.api import (
       deserialize_build_plan,
       dumps_json_dto,
       serialize_build_plan,
       serialize_build_result,
   )

   plan_dto: dict = serialize_build_plan(plan)
   response_body: str = dumps_json_dto(plan)

   # After SynBioSuite obtains approval and submits the DTO again:
   approved_plan = deserialize_build_plan(request_json)
   result = compiler.execute(approved_plan)
   result_dto: dict = serialize_build_result(result)

``serialize_build_plan`` and ``serialize_build_result`` return only JSON
primitives, lists, and dictionaries. ``dumps_json_dto`` emits deterministic
strict JSON. Schema version 1 uses ``"schema_version": "1.0"`` and the DTO
kinds ``"build_plan"`` and ``"build_result"``.

For a valid four-part Level-1 ComponentDefinition, planning includes the
canonical ``ordered_part_identities`` constraint. Any SBOL ordering warning is
preserved in ``ordering_warnings`` so an approved, deserialized plan executes
with the exact reviewed order.

The same module exports focused serializers for ``BuildRequest``,
``UnsupportedPlanningRecord``, ``StageResult``, warnings, missing inputs,
approvals, plasmids, backbones, strains, reagents, summaries, and reports.
Paths become strings, enums become their values, sets become sorted lists, and
dictionary keys are sorted. Live SBOL objects/documents and any credential,
token, client, resolver, or adapter fields are omitted.

Representative plan DTO
-----------------------

.. code-block:: json

   {
     "domestication_requests": [],
     "kind": "build_plan",
     "lvl1_requests": [
       {
         "constraints": {},
         "id": "assembly_lvl1:design",
         "parent_group": null,
         "source_display_id": "design",
         "source_identity": "https://example.org/design/1",
         "source_kind": "component_definition",
         "stage": "assembly_lvl1",
         "variant_index": null
       }
     ],
     "lvl2_requests": [],
     "schema_version": "1.0",
     "unsupported": [],
     "warnings": []
   }

Representative result DTO shape
-------------------------------

.. code-block:: json

   {
     "final_products": [],
     "graph": null,
     "kind": "build_result",
     "missing_inputs": [],
     "plan": {"kind": "build_plan", "schema_version": "1.0"},
     "report": null,
     "required_approvals": [],
     "schema_version": "1.0",
     "stage_results": [],
     "status": "success",
     "summary": null,
     "warnings": []
   }

The abbreviated nested plan above illustrates the shape only; an actual
``serialize_build_result`` response contains every required BuildPlan list.
