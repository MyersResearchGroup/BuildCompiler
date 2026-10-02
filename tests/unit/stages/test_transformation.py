import sbol2

from buildcompiler.api import BuildOptions, compile_plating, compile_transformation
from buildcompiler.domain import IndexedPlasmid, StageStatus
from buildcompiler.protocols import TransformationConfig
from buildcompiler.stages import TransformationStage


def test_transformation_stage_blocks_without_chassis_identity():
    result = TransformationStage().run(
        IndexedPlasmid(identity="plasmid_a"),
        source_document=sbol2.Document(),
        target_document=sbol2.Document(),
    )

    assert result.status == StageStatus.BLOCKED
    assert result.missing_inputs[0].missing_kind == "chassis"


def test_transformation_stage_returns_json_and_sbol_product():
    doc = sbol2.Document()
    plasmid = sbol2.ComponentDefinition("plasmid_a")
    doc.addComponentDefinition(plasmid)
    options = BuildOptions()
    options.transformation.chassis_identity = "dh5alpha"
    options.transformation.chassis_display_id = "dh5alpha"

    result = TransformationStage(options=options).run(
        IndexedPlasmid(
            identity=plasmid.identity,
            display_id=plasmid.displayId,
            sbol_component=plasmid,
        ),
        source_document=doc,
        target_document=sbol2.Document(),
    )

    assert result.status == StageStatus.SUCCESS
    assert result.products
    assert result.json_intermediate["Chassis"] == "dh5alpha"
    assert result.sbol_document.find(result.products[0].identity) is not None
    request = result.protocol_requests[0]
    assert request.source_stage_id == result.id
    assert request.reactions[0].strain.identity == result.products[0].identity
    assert request.reactions[0].plasmids[0].identity == plasmid.identity
    compiled = compile_transformation(result, config=TransformationConfig(replicates=1))
    assert compiled.manifest.samples[0].material.identity == result.products[0].identity
    plated = compile_plating(compiled.manifest)
    assert len(plated.manifest.samples) == 2
    assert "from pudu" not in compiled.script + plated.script
