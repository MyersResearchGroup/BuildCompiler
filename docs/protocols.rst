Native protocol compilation
===========================

``buildcompiler.protocols`` compiles assembly, transformation and plating requests
into review documents, structured handoffs and standalone robot scripts. Planning
and rendering require no robot SDK. Generated scripts import only Opentrons.

Structure and ownership
-----------------------

The package has two small subpackages. Each method keeps its configuration,
hardware profile, planner and well allocation in one file::

   protocols/
       __init__.py
       compiler.py
       inputs.py
       models.py
       methods/
           __init__.py
           assembly.py
           transformation.py
           plating.py
       backends/
           __init__.py
           markdown.py
           opentrons.py
           simulation.py
           _simulation_worker.py

``domain.protocol_requests`` defines immutable requests shared with build stages.
``inputs.py`` converts existing JSON and indexed stage records into those requests.
``models.py`` holds ``Sample``, shared operations such as ``Transfer`` and
``Distribute``, ``ProtocolPlan`` and ``OutputManifest``. A sample keeps its material
identity and parent sample IDs independently of its label and physical location.

``ProtocolCompiler.plan(request)`` calls the appropriate method planner and returns
a plan with unassigned sample locations. ``compile(request, profile=...)`` also
allocates wells, then sends that same plan to both renderers. The Opentrons renderer
emits Python directly from the operations and checks tip use and pipette capacity.
There is no second command representation between the plan and the script.

``CompiledProtocol`` contains ``plan``, ``script``, ``markdown``, ``manifest`` and a
read-only ``files`` mapping. ``write(directory)`` is the explicit filesystem
boundary. Compilation does not write files, simulate or mutate SBOL documents.
``backends.simulation.simulate_source`` runs the optional SDK in a subprocess.

Compiling stage results
-----------------------

Successful assembly and transformation stages include typed
``StageResult.protocol_requests`` alongside their existing JSON intermediates.
Given stage results for corresponding material identities:

.. code-block:: python

   from buildcompiler.api import (
       compile_assembly,
       compile_transformation,
       compile_plating,
   )
   from buildcompiler.protocols import OpentronsPlatingProfile

   assembled = compile_assembly(assembly_stage_result)
   transformed = compile_transformation(
       transformation_stage_result,
       inputs=assembled.manifest,
   )
   plated = compile_plating(
       transformed.manifest,
       profile=OpentronsPlatingProfile(
           thermocycler_labware="nest_96_wellplate_100ul_pcr_full_skirt",
       ),
   )

   assembled.write("results/assembly")
   transformed.write("results/transformation")
   plated.write("results/plating")

``OutputManifest`` represents planned outputs, not evidence that a run happened.
The transformation compiler preserves each assembly sample's ID as an upstream
source reference and rebinds its well to the source DNA plate. Every plasmid in
the request must exist in that manifest, with equal source-location replicate
counts. These multiply the configured transformation replicates; the two axes
are not interchangeable. Without an input manifest, DNA is allocated sequentially
on the temperature module.

The plating profile is explicit here because its standalone default uses a
different source plate definition from the transformation default. The
compiler does not infer a physical plate transfer from material identity.

Compiling existing JSON
-----------------------

.. code-block:: python

   from buildcompiler.protocols import (
       ProtocolCompiler,
       TransformationConfig,
       plasmid_manifest_from_json,
       transformation_request_from_json,
   )

   request = transformation_request_from_json(
       transformation_data,
       request_id="transformation",
   )
   config = TransformationConfig().with_overrides(explicit_overrides)
   compiled = ProtocolCompiler(transformation=config).compile(
       request,
       inputs=plasmid_manifest_from_json(plasmid_locations),
   )

``assembly_request_from_json`` accepts the existing assembly format.
``bacterium_manifest_from_json`` accepts the existing plating handoff; because
that format contains labels rather than material identities, the adapter assigns
local import identities instead of claiming those labels are SBOL URIs. Native
manifests retain identity and lineage throughout a workflow.

Each compilation returns ``protocol.py``, ``protocol.md``, ``manifest.json``,
``compilation.json`` and a method-specific JSON handoff. ``compilation.json``
records the resolved configuration, target profile and plan, including operation
kinds and sample locations. These files are also available in memory, for example
``compiled.files["manifest.json"]``. Writing refuses existing files unless
``overwrite=True`` is supplied explicitly.

Configuration and supported targets
------------------------------------

``AssemblyConfig``, ``TransformationConfig`` and ``PlatingConfig`` are separate
from their ``Opentrons*Profile`` hardware records. ``with_overrides`` applies
explicit keys, including ``False`` and default values, and rejects unknown keys.
Profiles validate deck collisions, well offsets and tip offsets. Compilation
rejects missing source bindings, duplicate placements, exhausted tips, unsupported
profiles and capacity violations detected by the supported target.

The supported targets use API 2.21 with fixed pipette models and supported labware
definitions. Profiles expose deck and starting-position configuration, rather than
arbitrary instrument substitution. Transformation and
plating each use one rack per pipette and reject batches that exhaust those racks.
Assembly retains its explicit rack replacement schedule.

Transformation's temperature operations carry an explicit simulation condition:
they appear in the plan and review document but are skipped during ordinary
simulation. ``water_testing=True`` omits those operations altogether.

Validation and migration boundary
----------------------------------

Install ``.[test,simulation]`` in Python 3.10 to run the pinned Opentrons 8.8.2
acceptance suite described in ``tests/automation/README.md``. The suite compares
the independent PUDU implementation with native output and tests the connected
three-stage handoff. It separately exercises transformation's temperature path
inside the simulator. Hardware and experimental outcomes are not tested.

The compiler returns structured artifacts explicitly; it does not produce Excel
workbooks or write handoff files during simulation. Legacy orchestration, notebook
APIs and the legacy manual plating summary remain compatibility surfaces; their automated
assembly, transformation and plating script writers use the native compiler.
Legacy multi-batch plating produces one standalone script per batch instead of
passing an unsupported ``batches`` object into a single protocol.

The MIT attribution is retained in the repository's ``LICENSE`` file.
