"""Regression coverage for planner-provided Level-1 part ordering."""

from __future__ import annotations

import sbol2

from buildcompiler.api import (
    BuildCompiler,
    BuildOptions,
    deserialize_build_plan,
    serialize_build_plan,
)
from buildcompiler.domain import (
    BuildStage,
    BuildStatus,
    IndexedBackbone,
    IndexedPlasmid,
    IndexedReagent,
    MaterialState,
)
from buildcompiler.execution import BuildContext, FullBuildExecutor
from buildcompiler.inventory import Inventory
from buildcompiler.sbol import AssemblySbolResult, SbolResolver
from buildcompiler.stages import AssemblyLvl1Stage


class _FakeAssemblyService:
    def run(self, job):
        return AssemblySbolResult(
            products=[
                IndexedPlasmid(
                    identity=f"{job.product_identity}/assembled",
                    display_id=f"{job.product_display_id}_assembled",
                    state=MaterialState.GENERATED,
                )
            ],
            stage_document=job.target_document,
            activity_identity="https://example.org/activities/lvl1",
            logs=["fake assembly completed"],
        )


def _lvl1_document() -> tuple[sbol2.Document, sbol2.ComponentDefinition, list[str]]:
    doc = sbol2.Document()
    roles = (
        ("promoter", "http://identifiers.org/so/SO:0000167"),
        ("rbs", "http://identifiers.org/so/SO:0000139"),
        ("cds", "http://identifiers.org/so/SO:0000316"),
        ("terminator", "http://identifiers.org/so/SO:0000141"),
    )
    parts = []
    for name, role in roles:
        part = sbol2.ComponentDefinition(f"https://example.org/parts/{name}")
        part.roles = [role]
        doc.addComponentDefinition(part)
        parts.append(part)

    design = sbol2.ComponentDefinition("https://example.org/designs/lvl1_target")
    for index, part in enumerate(parts, start=1):
        design.components.create(f"part{index}").definition = part.identity
    doc.addComponentDefinition(design)
    return doc, design, [part.identity for part in parts]


def _inventory(part_identities: list[str]) -> Inventory:
    plasmids = [
        IndexedPlasmid(
            identity=f"https://example.org/plasmids/part{index}",
            metadata={"insert_identities": [part_identity]},
        )
        for index, part_identity in enumerate(part_identities, start=1)
    ]
    return Inventory(
        plasmids=plasmids,
        backbones=[
            IndexedBackbone(
                identity="https://example.org/backbones/lvl1",
                metadata={"stage": BuildStage.ASSEMBLY_LVL1.value},
            )
        ],
        reagents=[
            IndexedReagent(
                identity="https://example.org/reagents/bsai",
                name="BsaI",
                reagent_type="restriction_enzyme",
            ),
            IndexedReagent(
                identity="https://example.org/reagents/ligase",
                name="T4_DNA_ligase",
                reagent_type="ligase",
            ),
        ],
    )


def _compiler(doc: sbol2.Document, part_identities: list[str]) -> BuildCompiler:
    inventory = _inventory(part_identities)
    options = BuildOptions()
    executor = FullBuildExecutor(
        context=BuildContext(
            sbol=SbolResolver(doc),
            inventory=inventory,
            build_document=doc,
            options=options,
        ),
        lvl1_stage=AssemblyLvl1Stage(
            inventory=inventory,
            options=options,
            assembly_service=_FakeAssemblyService(),
        ),
    )
    return BuildCompiler(
        inventory=inventory,
        sbol_document=doc,
        executor=executor,
        options=options,
    )


def test_clean_api_plan_execute_and_round_trip_preserve_lvl1_constraints():
    doc, design, part_identities = _lvl1_document()
    compiler = _compiler(doc, part_identities)

    plan = compiler.plan([design])
    request = plan.lvl1_requests[0]

    assert request.constraints["ordered_part_identities"] == part_identities
    assert compiler.execute(plan).status == BuildStatus.SUCCESS

    restored_plan = deserialize_build_plan(serialize_build_plan(plan))

    assert restored_plan.lvl1_requests[0].constraints == request.constraints

    restored_doc, _, restored_part_identities = _lvl1_document()
    restored_compiler = _compiler(restored_doc, restored_part_identities)

    assert restored_compiler.execute(restored_plan).status == BuildStatus.SUCCESS
