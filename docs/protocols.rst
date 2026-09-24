Native protocol compilation
===========================

``buildcompiler.protocols`` compiles assembly, transformation and plating requests
into review documents, structured handoffs and standalone OT-2 protocols. Planning
and rendering require no robot SDK. Python protocols import only Opentrons; JSON
protocols embed their labware definitions and require no Python entrypoint.

Structure and ownership
-----------------------

The package has two small subpackages. Each method keeps its input decoding,
configuration, hardware profile, planner and well allocation in one file::

   protocols/
       __init__.py
       compiler.py
       models.py
       methods/
           __init__.py
           assembly.py
           transformation.py
           plating.py
       backends/
           __init__.py
           markdown.py
           opentrons_ot2_python.py
           opentrons_ot2_json.py
           simulation.py
           _simulation_worker.py

``domain.protocol_requests`` defines immutable requests shared with build stages.
Each method module converts its JSON or indexed stage records into those requests.
``MaterialRef.from_identity`` supplies shared identity and display-label handling.
``methods.__init__`` shares reaction-list validation, sequential well placement and
upstream well binding. Methods retain their field decoding, sample selection,
allocation policy and operation order.
``models.py`` holds ``Sample``, shared operations such as ``Transfer`` and
``Distribute``, ``ProtocolPlan`` and ``OutputManifest``. A sample keeps its material
identity and parent sample IDs independently of its label and physical location.

``ProtocolCompiler.plan(request)`` calls the appropriate method planner and returns
a plan with unassigned sample locations. ``compile(request, profile=...)`` also
allocates wells, then sends that same plan to Markdown and the selected robot
backend. Both robot backends check tip use and pipette capacity. The Python backend
emits SDK calls; the JSON builder expands operations into validated vendor commands,
including refills, mixing, air gaps, trash movements and module waits.

``CompiledProtocol`` exposes ``plan``, ``source``, ``backend``, ``protocol_filename``,
``markdown``, ``manifest`` and a read-only ``files`` mapping. ``script`` remains an
alias for the serialized source for existing callers. ``write(directory)`` is the explicit filesystem
boundary. Compilation does not write files, simulate or mutate SBOL documents.
``backends.simulation.analyze_source`` runs either format through the optional
Protocol Engine simulator in a subprocess. ``simulate_source`` retains the
Python SDK trace used by the original acceptance tests.

Choosing the robot format
------------------------

Install ``.[automation]`` for JSON compilation, simulation and inventory integration.
This includes ``opentrons-shared-data==8.8.2`` for offline schemas and labware
definitions. The default backend remains ``opentrons_ot2_python``.
Select ``opentrons_ot2_json`` on ``ProtocolCompiler.compile`` or any of
``compile_assembly``, ``compile_transformation`` and ``compile_plating``:

.. code-block:: python

   from buildcompiler.protocols import ProtocolCompiler

   compiled = ProtocolCompiler().compile(
       request,
       backend="opentrons_ot2_json",
   )
   compiled.write("results/protocol")  # Includes protocol.json.

Both formats use the same allocated plan, review document and output manifest.
The JSON backend uses protocol schema 8, command schema 10 and labware schema 2,
qualified against Opentrons 8.8.2. It pins labware versions, pipette flow rates and
tip overlap to the Python API 2.21 behavior used by the hardware profiles.
Conical-source heights are computed from planned volume changes at each
distribution boundary, including disposal volumes consumed by refills.

Simulation remains an explicit action, separate from compilation:

.. code-block:: python

   from buildcompiler.protocols.backends.simulation import analyze_source

   analysis = analyze_source(compiled.source, format="json")

The equivalent CLI is ``python -m opentrons.cli analyze protocol.json --check
--json-output analysis.json``. Use Python 3.10 with ``.[automation]`` for either
simulation entrypoint. ``opentrons.simulate.simulate`` does not accept modern JSON
protocols.

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

Each compilation returns ``protocol.py`` or ``protocol.json``, plus ``protocol.md``, ``manifest.json``,
``compilation.json`` and a method-specific JSON handoff. ``compilation.json``
records the selected backend, resolved configuration, target profile and plan, including operation
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

Transformation's temperature operations retain the Python simulation condition:
they appear in the plan and review document but are skipped during ordinary Python
simulation. JSON always contains the execution temperature program, and its
analysis exercises it. ``water_testing=True`` omits these operations in both formats.

Validation and migration boundary
----------------------------------

Install ``.[test,automation]`` in Python 3.10 to run the pinned Opentrons 8.8.2
acceptance suite described in ``tests/automation/README.md``. The suite compares
the independent PUDU implementation with both native formats and tests the connected
three-stage handoff. Protocol Engine comparisons retain resource geometry, positions,
volumes, flow rates, tip boundaries and temperature programs. Transformation's full
temperature path is enabled in both Python references for these comparisons.
The original Python SDK comparisons remain in place. Hardware and experimental
outcomes are not tested.

The compiler returns structured artifacts explicitly; it does not produce Excel
workbooks or write handoff files during simulation. Legacy orchestration, notebook
APIs and the legacy manual plating summary remain compatibility surfaces; their automated
assembly, transformation and plating script writers use the native compiler.
Legacy multi-batch plating produces one standalone script per batch instead of
passing an unsupported ``batches`` object into a single protocol.

The MIT attribution is retained in the repository's ``LICENSE`` file.
