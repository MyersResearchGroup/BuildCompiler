SBOL provenance
===============

BuildCompiler records relationships between biological entities, the activities
that use and generate them, and the agents and plans associated with those
activities. These relationships live in an SBOL 2 document and use the PROV-O
vocabulary. They let a consumer trace a generated product back to its inputs and
the activity responsible for it.

This guide describes the current implementation, including differences between
stages and incomplete references. The main entry points are
:mod:`buildcompiler.sbol.assembly`, :mod:`buildcompiler.sbol.transformation`, and
:mod:`buildcompiler.sbol.domestication`. Assembly still delegates to
:mod:`buildcompiler.sbol2build`. The older compiler and transformation helpers
have related, but different, output behavior.

.. contents:: On this page
   :local:
   :depth: 2

What the records establish
--------------------------

The graph can answer questions such as:

* Which implementation was used as an input to an activity?
* Which biological definition does that implementation represent?
* Which activity generated a product implementation?
* Which agent and plan are associated with that activity?
* Which earlier definition or sequence was a generated entity derived from?

These are compiler records. Creating an ``Implementation`` or assigning
``wasGeneratedBy`` during compilation does not establish that laboratory work
occurred. The assembly service computes candidate products in software. The
transformation service creates a projected strain record and explicitly returns
``state_evidence="protocol_generated_not_executed"`` in its product metadata.
Both services return products with ``MaterialState.GENERATED``.

The recorded agent is currently the generic ``Agent("BuildCompiler")``. It does
not identify an operator, a robot, an authenticated user, a particular software
release, or an individual compiler invocation. ``StageStatus.SUCCESS`` means a
compiler stage succeeded; it does not certify a successful physical experiment.
The current services do not populate execution timestamps or measured outcomes.

Objects and relationships
-------------------------

Biological descriptions and realizations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: Objects used by BuildCompiler
   :header-rows: 1
   :widths: 26 74

   * - SBOL/Python object
     - Role in this codebase
   * - ``ComponentDefinition``
     - Describes a part, plasmid, or reagent. References to sequences and child
       components describe its content and structure.
   * - ``Sequence``
     - Stores sequence data referenced by a component definition.
   * - ``ModuleDefinition``
     - Describes a chassis or projected transformed strain. The transformation
       service links a strain to its chassis module and plasmid definition.
   * - ``Implementation``
     - Represents a realization of a component or module. Its ``built`` reference
       selects that definition. Compiler-created realizations can be prospective.
   * - ``Activity``
     - Records a generating operation, such as assembly or transformation.
   * - ``Usage``
     - Connects an activity to an input entity and records that entity's role.
   * - ``Association``
     - Connects an activity to its responsible agent and, when present, its plan.
   * - ``Agent`` and ``Plan``
     - Identify the responsible actor and the description of the intended work.

The inventory index groups implementations by ``implementation.built``. Several
implementations can therefore refer to the same definition. An indexed plasmid's
``identity`` is normally the definition URI; its
``metadata["implementation_identity"]`` identifies the selected implementation
when that metadata is available. Do not substitute a display label or definition
URI for an implementation URI when following material usage.

The distinction follows the SBOL 2 ``Implementation`` model; see section 7.12 of
the `SBOL 2.3 specification <https://sbolstandard.org/docs/SBOL2.3.0.pdf>`_.

Edges and their direction
~~~~~~~~~~~~~~~~~~~~~~~~~

In the table below, ``sbol:`` means ``http://sbols.org/v2#`` and ``prov:`` means
``http://www.w3.org/ns/prov#``. The RDF names are useful when inspecting exported
RDF/XML or querying its triples. The Python names are the properties used by
BuildCompiler and pySBOL2.

.. list-table:: Relationships to follow
   :header-rows: 1
   :widths: 30 28 42

   * - Python property
     - RDF predicate
     - Direction
   * - ``implementation.built``
     - ``sbol:built``
     - Implementation to ComponentDefinition or ModuleDefinition.
   * - ``entity.wasGeneratedBy``
     - ``prov:wasGeneratedBy``
     - Generated entity to Activity; used here on product implementations.
   * - ``activity.usages``
     - ``prov:qualifiedUsage``
     - Activity to Usage.
   * - ``usage.entity``
     - ``prov:entity``
     - Usage to the input entity, normally an Implementation here.
   * - ``usage.roles``
     - ``prov:hadRole``
     - Usage to role URI(s).
   * - ``activity.associations``
     - ``prov:qualifiedAssociation``
     - Activity to Association.
   * - ``association.agent``
     - ``prov:agent``
     - Association to Agent.
   * - ``association.plan``
     - ``prov:hadPlan``
     - Association to Plan.
   * - ``association.roles``
     - ``prov:hadRole``
     - Association to agent-role URI(s); currently unpopulated by these services.
   * - ``entity.wasDerivedFrom``
     - ``prov:wasDerivedFrom``
     - Derived entity to its source entity or entities.
   * - ``activity.types``
     - ``sbol:type``
     - Activity to activity-type URI(s).

The resulting shape is:

.. code-block:: text

   Output Implementation --built----------> Output definition
             |
        wasGeneratedBy
             |
             v
          Activity --usages--> Usage --entity--> Input Implementation
             |                  |                        |
        associations          roles                    built
             |                  |                        |
             v                  v                        v
         Association         Role URI              Input definition
             |      |
           agent   plan
             |      |
             v      v
           Agent   Plan

``wasDerivedFrom`` adds entity-to-entity lineage alongside this structure. For
example, an extracted definition can refer to its source definition without
introducing a separate generating activity. A derivation edge alone does not
identify an agent, plan, or exact operation.

In pySBOL2, ``built``, ``usage.entity``, ``association.agent``, and
``association.plan`` are scalar URI references. ``wasGeneratedBy``,
``wasDerivedFrom``, and ``roles`` are list-valued. ``usages`` and ``associations``
are collections of owned objects: iterate them directly, then resolve their URI
references through the document. Even when a service creates one activity for a
product, readers should iterate ``wasGeneratedBy`` rather than treat it as a
string. Empty collections and missing optional references are possible.
Some pySBOL2 versions, including 1.4.1, expose ``Activity.types`` as a scalar URI
or ``None``; the reader below preserves that value rather than iterating it.

BuildCompiler writes the qualified paths through ``Usage`` and ``Association``.
Its writers do not explicitly add shortcut ``prov:used`` or
``prov:wasAssociatedWith`` triples. Queries should follow the qualified paths
rather than depend on a reasoner materializing shortcuts. The vocabulary and
qualified relationship pattern are described in the
`W3C PROV-O specification <https://www.w3.org/TR/prov-o/#description-qualified-terms>`_.

What each stage records
-----------------------

.. list-table:: Current stage coverage
   :header-rows: 1
   :widths: 21 45 34

   * - Stage
     - Records produced
     - Limits
   * - Assembly levels 1 and 2
     - Product definitions, sequences, implementations, and an assembly activity
       with input usages and an agent/plan association.
     - Agent and plan references are assigned, but their top-level objects are
       not added by the assembly writer. A separate output document need not
       contain the referenced inputs.
   * - Transformation
     - Strain module, implementation, activity, two input usages, association,
       agent, and plan; immediate input definitions and implementations are also
       added to the target document when absent.
     - Describes a projected strain. It does not recursively copy upstream
       provenance or all objects referenced by input definitions.
   * - Domestication
     - Product and insert definitions, sequences, a product implementation, an
       insert derivation link, and detailed Python metadata.
     - No generating activity, usage, association, agent, or plan is created by
       this service. The product implementation has no assigned ``wasGeneratedBy``.
   * - Plating artifacts
     - Plate maps and optional manual or PUDU protocol artifacts.
     - The legacy ``BuildCompiler.plating`` method is file/metadata oriented and
       does not create new SBOL objects.

Assembly
~~~~~~~~

:class:`buildcompiler.sbol.assembly.AssemblyService` adapts indexed inventory
records and invokes :class:`buildcompiler.sbol2build.Assembly`. Both assembly
levels use this path. The wrapper first uses an explicit implementation identity
when supplied, otherwise finds an implementation whose ``built`` matches the
definition. The underlying assembly code uses the first implementation in each
adapted plasmid's implementation list. This is selection of an input record,
not a record of aliquot withdrawal or inventory consumption.

``initialize_assembly_activity()`` creates one activity named from the composite
prefix, with ``types="http://sbols.org/v2#build"``. Part and backbone processing
append usages for their implementations and restriction enzyme; ligation appends
a ligase usage. These usages use the ``sbol:build`` role. The steps contribute to
one assembly activity rather than separate digestion and ligation activities.
Each resulting product implementation points to that activity and to its product
definition through ``wasGeneratedBy`` and ``built`` respectively.

Intermediate definitions and sequences record selected ``wasDerivedFrom`` links,
including extracted parts, overhangs, and assembly scars. These links do not imply
that every generated object has a complete derivation chain. Intermediate
extracts are added to the source document; ``include_extracted_parts=True`` also
adds them to the final document. Product definitions, sequences, and
implementations are added to both documents; the activity is added to the final
document.

The association references ``Agent("BuildCompiler")`` and ``Plan("assembly_plan")``.
The plan description is currently the fixed string
``MoClo DNA Assembly With Opentrons OT2``. That label does not establish which
protocol output mode was selected or whether an OT-2 was used. These top-level agent
and plan objects are created locally but not added to the documents by this
writer, so their references can remain unresolved after serialization.

Transformation
~~~~~~~~~~~~~~

:class:`buildcompiler.sbol.transformation.TransformationService` creates a strain
``ModuleDefinition`` containing a ``Module`` reference to the chassis and a
``FunctionalComponent`` reference to the plasmid definition. Its
``wasDerivedFrom`` points to the chassis module. Plasmid participation is recorded
through the functional component and activity usage, not an additional
``wasDerivedFrom`` value on the strain module.

The activity has exactly two usages: the chassis implementation and the plasmid
implementation. Both have the ``sbol2.SBO_REACTANT`` role. Unlike the assembly
writer, this service does not set ``activity.types``. It adds a BuildCompiler
agent and a product-specific plan to the target document, along with the
activity, product, and immediate inputs. The plan description is generic text;
it is not a serialized robot protocol.

Missing input implementations can be synthesized as placeholder records with
``built`` references, and a missing chassis module can also be created. Such
records do not establish that a physical sample exists or that its earlier
history is known. The output metadata includes implementation and activity
identities, ``projected_state="transformed"``, and
``state_evidence="protocol_generated_not_executed"``. Those metadata fields belong
to the Python result; this service does not encode them as SBOL annotations.

Domestication and older entry points
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:class:`buildcompiler.sbol.domestication.DomesticationService` assigns
``insert_component.wasDerivedFrom`` to the source component and sets the product
implementation's ``built`` reference. Source-part, backbone, reagent, insert,
and sequence-edit information is returned in product metadata and the
``artifacts["domestication"]`` dictionary. Those dictionary entries are not
automatically equivalent to RDF provenance edges. In particular, consumers
cannot recover a generating activity for this product from ``wasGeneratedBy``.

Older entry points must be interpreted according to their own writers:

* The effective ``buildcompiler.buildcompiler.BuildCompiler.transformation``
  method delegates to ``sbol2build.Transformation.chemical_transformation``.
  An earlier definition of the same method in the file is shadowed and does not
  determine the current runtime behavior.
* ``buildcompiler.transformation.bacterial_transformation`` adds its plan but
  does not explicitly add its agent.
* ``buildcompiler.sbol2build.Transformation.chemical_transformation`` records
  usages and generated implementations without an agent/plan association.

Do not infer identical provenance coverage from a shared stage name. This guide's
transformation example uses the modular ``TransformationService``.

Identity, document ownership, and export
----------------------------------------

Use the full URI returned by ``object.identity`` as the graph key. Names and
``displayId`` values are labels and need not be globally unique. BuildCompiler's
legacy assembly module configures pySBOL2's global homespace and URI options at
import time; callers can also change those settings. The examples therefore use
returned identities rather than reconstructing URIs from strings.

Generated IDs are generally based on product names or input identities, not on
unique run IDs. The generic agent and assembly-plan identities can be shared
across products. Repeating work in the same document may reuse existing objects
where a writer checks for them, or raise a duplicate-identity error where it does
not. These IDs do not provide an append-only history of repeated experiments.

The services mutate the supplied documents. In the full-build executor, stages
receive the shared ``context.build_document`` as their target. A
``StageResult.sbol_document`` may therefore refer to the cumulative live document
and acquire objects from later stages. It is not necessarily an independent
snapshot containing only that stage's results.

An SBOL reference stores a URI; assigning it does not automatically copy the
referenced top-level object or its dependencies into the document. As a result:

* ``document.find(uri) is None`` means the object is unavailable in that document,
  not that the provenance edge is absent.
* Assembly output can require its original inventory document to resolve inputs.
* Transformation copies immediate inputs but can leave their sequences, nested
  definitions, or earlier generating activities outside the target document.
* The SynBioHub hydration helper follows selected structural references such as
  ``built`` and component definitions. It does not walk the complete PROV graph.

Applications that need a self-contained archive must explicitly collect and
check the referenced objects. A successful RDF/XML round trip preserves stored
references; it does not establish that all references resolve or that the
biological and provenance assertions are correct.

``FullBuildResult.build_document`` carries the cumulative SBOL document.
``serialize_build_result()`` deliberately omits live SBOL documents and objects
from its JSON DTO. Preserve the SBOL serialization separately from the result
JSON when both the graph and compiler metadata are needed. Writing an existing
document is an explicit caller action, for example:

.. code-block:: python

   # full_result is a FullBuildResult returned by the compiler.
   full_result.build_document.write("build.xml")

An SBOL ``Plan``, the planning module's ``BuildPlan``, and the typed protocol
specifications in ``buildcompiler.domain.protocol`` are different objects.
Current SBOL plans do not reference generated protocol files or their manifest
hashes. See :doc:`examples/transformation_pudu` for the PUDU protocol workflow
and :doc:`synbiosuite_integration` for JSON DTOs.

Following provenance in Python
------------------------------

The following offline example creates minimal descriptive inputs and calls the
modular transformation service. It demonstrates graph construction without
sequences, protocol compilation, network access, or laboratory execution. Run
the snippets in this section in order in a Python environment with BuildCompiler
installed.

.. code-block:: python

   import sbol2

   from buildcompiler.domain import IndexedPlasmid
   from buildcompiler.sbol import TransformationJob, TransformationService

   source = sbol2.Document()
   target = sbol2.Document()
   plasmid = sbol2.ComponentDefinition("example_plasmid")
   chassis = sbol2.ModuleDefinition("example_chassis")
   plasmid_impl = sbol2.Implementation("example_plasmid_impl")
   chassis_impl = sbol2.Implementation("example_chassis_impl")
   plasmid_impl.built = plasmid.identity
   chassis_impl.built = chassis.identity
   for obj in (plasmid, chassis, plasmid_impl, chassis_impl):
       source.add(obj)

   result = TransformationService().run(
       TransformationJob(
           plasmid=IndexedPlasmid(
               identity=plasmid.identity,
               display_id=plasmid.displayId,
               sbol_component=plasmid,
               metadata={"implementation_identity": plasmid_impl.identity},
           ),
           chassis_identity=chassis.identity,
           chassis_display_id=chassis.displayId,
           source_document=source,
           target_document=target,
       )
   )

   document = result.stage_document
   output_uri = result.product.metadata["implementation_identity"]
   output = document.find(output_uri)
   assert output.built == result.product.identity
   assert list(output.wasGeneratedBy) == [result.activity_identity]
   assert result.product.metadata["state_evidence"] == (
       "protocol_generated_not_executed"
   )

Start from the output implementation and follow its generating activities. This
reader retains unresolved URI references instead of treating missing objects as
evidence that no input or agent was recorded:

.. code-block:: python

   def inspect_provenance(document, implementation_uri):
       implementation = document.find(implementation_uri)
       if not isinstance(implementation, sbol2.Implementation):
           raise ValueError(f"Implementation not found: {implementation_uri}")

       def reference(uri):
           return {"uri": uri, "resolved": bool(uri) and document.find(uri) is not None}

       activities = []
       for activity_uri in implementation.wasGeneratedBy:
           activity = document.find(activity_uri)
           record = reference(activity_uri)
           if isinstance(activity, sbol2.Activity):
               record["types"] = activity.types
               record["inputs"] = []
               for usage in activity.usages:
                   entity = document.find(usage.entity)
                   record["inputs"].append({
                       "usage": usage.identity,
                       "entity": reference(usage.entity),
                       "roles": list(usage.roles),
                       "built": reference(entity.built)
                       if isinstance(entity, sbol2.Implementation) else None,
                   })
               record["associations"] = [
                   {
                       "association": association.identity,
                       "agent": reference(association.agent),
                       "plan": reference(association.plan),
                       "roles": list(association.roles),
                   }
                   for association in activity.associations
               ]
           activities.append(record)
       return {
           "implementation": implementation.identity,
           "built": reference(implementation.built),
           "activities": activities,
       }

   provenance = inspect_provenance(document, output_uri)
   activity = provenance["activities"][0]
   assert {item["entity"]["uri"] for item in activity["inputs"]} == {
       plasmid_impl.identity, chassis_impl.identity,
   }
   assert activity["associations"][0]["agent"]["resolved"]
   assert activity["associations"][0]["plan"]["resolved"]

For assembly results, product metadata does not currently include the product
implementation identity. Find implementations whose ``built`` equals the product
definition identity, then inspect each candidate; more than one can exist.
To follow multiple stages, repeat the inspection for each input implementation
that has ``wasGeneratedBy`` references. Track visited identities when traversing
imported graphs, and report unresolved references explicitly.

The generation edge points from output to activity. To find all outputs of an
activity, search implementations for that activity URI. The following also checks
that the example's generation references survive serialization:

.. code-block:: python

   generated = [
       impl.identity for impl in document.implementations
       if result.activity_identity in impl.wasGeneratedBy
   ]
   assert output_uri in generated

   restored = sbol2.Document()
   restored.readString(document.writeString())
   restored_output = restored.find(output_uri)
   assert list(restored_output.wasGeneratedBy) == [result.activity_identity]
   restored_provenance = inspect_provenance(restored, output_uri)
   assert restored_provenance["activities"][0]["associations"][0]["agent"]["resolved"]

The order of XML elements and list-valued references is not an event timeline.
The current services do not set ``wasInformedBy`` between stage activities;
cross-stage history is obtained through shared input/output implementation URIs.
Finding an empty history can mean an imported input has no recorded history, a
placeholder was synthesized, or a stage does not emit activities.

Reporting graph and validation boundaries
-----------------------------------------

:mod:`buildcompiler.reporting.graph` constructs ``FullBuildResult.graph`` from
stage results, products, missing inputs, and approvals. Its ``requires``,
``produces``, and ``blocks`` edges are a reporting summary. It does not traverse
the SBOL provenance graph or include its agents, plans, and qualified usages.
Neither graph is the full-build scheduler; orchestration lives in the executor.

When assessing an exported provenance record, distinguish three checks:

1. **Serialization:** can the RDF/XML be read, and are the expected identities and
   edges preserved?
2. **Reference completeness:** do input, output, activity, agent, plan, and
   structural references resolve in the intended set of documents?
3. **Semantic evidence:** do the roles, stage metadata, and independent execution
   records support the interpretation being made?

The traversal example checks selected references, not full SBOL conformance.
The current assembly activity is typed ``sbol:build`` while its association has
no role. SBOL 2.3 specifies a corresponding association role for a typed build
activity (rule ``sbol-12414``); the present writer should not be taken as proof of
complete standards compliance. Strict validation must also account for unresolved
agent/plan references and the particular validator configuration. See section
13.1 and Appendix A of the
`SBOL 2.3 specification <https://sbolstandard.org/docs/SBOL2.3.0.pdf>`_.

Existing checks cover selected behavior:

* ``tests/unit/sbol/test_transformation_service.py`` checks the product's
  implementation, generating activity, and projected-state metadata.
* ``tests/unit/sbol/test_assembly_service.py`` checks the service contract with a
  mocked assembly implementation; it does not establish completeness of the
  real assembly graph.
* ``test_ligation`` in ``tests/test_core.py`` checks reagent/input usages and
  output generation links in the older test suite, which requires SynBioHub
  access and credentials.

These checks do not establish physical execution, a complete history across all
stages, or a self-contained export. Those limits are part of the current model
and should remain visible to downstream consumers.

Implementation map
------------------

.. list-table:: Where to inspect or change the behavior
   :header-rows: 1
   :widths: 43 57

   * - Module
     - Responsibility
   * - :mod:`buildcompiler.sbol2build`
     - Assembly activities, usages, derivation links, and product implementations.
   * - :mod:`buildcompiler.sbol.assembly`
     - Indexed input selection and normalized assembly results.
   * - :mod:`buildcompiler.sbol.transformation`
     - Modular transformation provenance and projected-strain metadata.
   * - :mod:`buildcompiler.sbol.domestication`
     - Domestication derivation and result metadata.
   * - :mod:`buildcompiler.inventory.indexing`
     - Mapping implementations to biological definitions and inventory records.
   * - :mod:`buildcompiler.domain.build_result`
     - Stage and full-build result containers.
   * - :mod:`buildcompiler.execution.executor`
     - Shared build document, stage orchestration, and reporting integration.
   * - :mod:`buildcompiler.api.serialization`
     - JSON DTO boundary that omits live SBOL documents.
   * - :mod:`buildcompiler.reporting.graph`
     - Separate reporting graph.

Changes to these writers should update this guide alongside the relevant tests,
particularly when adding activity coverage, execution evidence, configurable
agents, or complete document export.
