Native protocol compilation
===========================

``buildcompiler.protocols`` owns the assembly, transformation and plating methods
previously supplied by PUDU's ``SBOLLoopAssembly``, ``HeatShockTransformation``
and ``Plating`` classes. The planners, allocation records and artifact renderer
require neither PUDU nor the Opentrons SDK. Generated robot scripts import only
Opentrons. The old automated script writers also delegate to this compiler.

Structure and ownership
-----------------------

* ``domain.protocol_requests`` defines frozen ``MaterialRef``,
  ``AssemblyReaction``, ``TransformationReaction`` and method-specific request
  records. Requests retain full material identities and ordered components.
* ``protocols.methods`` contains pure planners and their immutable configurations.
  ``TransformationConfig`` owns transformation parameters; its planner owns
  chassis grouping, tube consumption and the two replicate axes.
* ``protocols.materials`` and ``protocols.steps`` define samples and shared
  operations: transfer, distribute, mix, tip lifecycle and module operations.
  ``ProtocolPlan`` records explicit inputs, intermediates, outputs and lineage.
* ``protocols.allocation`` defines container-qualified placements and output
  manifests. Sample identity does not depend on a display label or well name.
* ``protocols.backends.opentrons`` owns supported hardware profiles, allocation,
  tip scheduling, shared operation lowering and standalone source rendering.
  It emits immutable ``OpentronsProgram`` records before rendering Python.
* ``protocols.backends.markdown`` describes the same logical plan and allocation.
  ``ArtifactBundle.write`` is the explicit filesystem boundary. Compilation does
  not simulate, write files, or mutate SBOL documents.

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

   assembled.artifacts.write("results/assembly")
   transformed.artifacts.write("results/transformation")
   plated.artifacts.write("results/plating")

``OutputManifest`` represents planned outputs, not evidence that a run happened.
The transformation compiler preserves each assembly sample's ID as an upstream
source reference and rebinds its well to the source DNA plate. Every plasmid in
the request must exist in that manifest, with equal source-location replicate
counts. These multiply the configured transformation replicates; the two axes
are not interchangeable. Without an input manifest, DNA is allocated sequentially
on the temperature module.

The plating profile is explicit here because PUDU's standalone plating default
uses a different source plate definition from its transformation default. The
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
records the resolved configuration, target profile, typed operation kinds,
containers, placements and PUDU reference revision. Writing refuses existing
files unless ``overwrite=True`` is supplied explicitly.

Configuration and supported targets
------------------------------------

``AssemblyConfig``, ``TransformationConfig`` and ``PlatingConfig`` are separate
from their ``Opentrons*Profile`` hardware records. ``with_overrides`` applies
explicit keys, including ``False`` and default values, and rejects unknown keys.
Profiles validate deck collisions, well offsets and tip offsets. Compilation
rejects missing source bindings, duplicate placements, exhausted tips, unsupported
profiles and capacity violations detected by the supported target.

The initial targets preserve PUDU's API 2.21 hardware choices, pipettes and labware.
They expose deck and starting-position configuration; they do not promise support
for arbitrary replacement instruments or labware definitions. Transformation and
plating each use one rack per pipette and reject batches that exhaust those racks.
Assembly retains its explicit rack replacement schedule.

PUDU's default transformation simulation skips temperature operations. The native
plan retains those operations with an explicit simulation condition, so both the
review document and script show the distinction. ``water_testing=True`` omits
those operations altogether.

Validation and migration boundary
----------------------------------

Install ``.[test,simulation]`` in Python 3.10 to run the pinned Opentrons 8.8.2
acceptance suite described in ``tests/automation/README.md``. The suite compares
the independent PUDU implementation with native output and tests the connected
three-stage handoff. It separately exercises transformation's temperature path
inside the simulator. Hardware and experimental outcomes are not tested.

The native compiler does not reproduce PUDU's Excel presentation or simulation-time
file writes. It returns structured artifacts explicitly. Other PUDU protocol
families are outside this migration. Legacy orchestration, notebook APIs and the
legacy manual plating summary remain compatibility surfaces; their automated
assembly, transformation and plating script writers use the native compiler.
Legacy multi-batch plating produces one standalone script per batch instead of
passing an unsupported ``batches`` object into a single protocol.

PUDU's MIT attribution is retained in ``protocols.attribution`` and generated
scripts.
