import sbol2

from buildcompiler.domain import IndexedPlasmid, IndexedStrain, MaterialState
from buildcompiler.sbol import TransformationJob, TransformationService


def test_transformation_service_returns_transformed_strain_with_sbol_provenance():
    source = sbol2.Document()
    target = sbol2.Document()
    plasmid = sbol2.ComponentDefinition("plasmid_a")
    source.addComponentDefinition(plasmid)
    plasmid_impl = sbol2.Implementation("plasmid_a_impl")
    plasmid_impl.built = plasmid.identity
    source.addImplementation(plasmid_impl)
    chassis = sbol2.ModuleDefinition("dh5alpha")
    source.addModuleDefinition(chassis)
    chassis_impl = sbol2.Implementation("dh5alpha_impl")
    chassis_impl.built = chassis.identity
    source.addImplementation(chassis_impl)

    result = TransformationService().run(
        TransformationJob(
            plasmid=IndexedPlasmid(
                identity=plasmid.identity,
                display_id=plasmid.displayId,
                metadata={"implementation_identity": plasmid_impl.identity},
                sbol_component=plasmid,
            ),
            chassis_identity=chassis.identity,
            chassis_display_id=chassis.displayId,
            source_document=source,
            target_document=target,
        )
    )

    assert isinstance(result.product, IndexedStrain)
    assert result.product.state == MaterialState.TRANSFORMED
    assert result.product.metadata["plasmid_identity"] == plasmid.identity
    assert target.find(result.product.identity) is not None
    implementation = target.find(result.product.metadata["implementation_identity"])
    assert isinstance(implementation, sbol2.Implementation)
    assert implementation.wasGeneratedBy == result.activity_identity
    assert isinstance(target.find(result.activity_identity), sbol2.Activity)
