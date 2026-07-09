import sbol2

from buildcompiler.api import BuildOptions, ProtocolMode
from buildcompiler.domain import BuildRequest, BuildStage, DesignKind, IndexedBackbone, IndexedReagent, StageStatus
from buildcompiler.inventory import Inventory
from buildcompiler.stages import DomesticationStage


def _request(identity: str = "part") -> BuildRequest:
    return BuildRequest("req-1", BuildStage.DOMESTICATION, identity, "part", DesignKind.COMPONENT_DEFINITION)


def _source_doc(identity: str = "part", seq: str = "ATGGGTCTCAA") -> sbol2.Document:
    doc = sbol2.Document()
    part = sbol2.ComponentDefinition(identity)
    part.roles = "http://identifiers.org/so/SO:0000167"
    seq_obj = sbol2.Sequence(f"{identity}_seq")
    seq_obj.elements = seq
    seq_obj.encoding = sbol2.SBOL_ENCODING_IUPAC
    doc.addSequence(seq_obj)
    part.sequences = seq_obj.identity
    doc.addComponentDefinition(part)
    return doc


def _inventory(with_backbone=True, with_enzyme=True, with_ligase=True) -> Inventory:
    backbones = [IndexedBackbone("bb", metadata={"stage": BuildStage.DOMESTICATION.value})] if with_backbone else []
    reagents = []
    if with_enzyme:
        reagents.append(IndexedReagent("e1", name="BsaI", reagent_type="restriction_enzyme"))
    if with_ligase:
        reagents.append(IndexedReagent("l1", name="T4_DNA_ligase", reagent_type="ligase"))
    return Inventory(backbones=backbones, reagents=reagents)


def test_blocked_when_backbone_missing() -> None:
    stage = DomesticationStage(inventory=_inventory(with_backbone=False))
    result = stage.run(_request(), source_document=_source_doc(), target_document=sbol2.Document())
    assert result.status == StageStatus.BLOCKED
    assert result.missing_inputs[0].missing_kind == "backbone"


def test_blocked_when_reagents_missing() -> None:
    stage = DomesticationStage(inventory=_inventory(with_enzyme=False, with_ligase=False))
    result = stage.run(_request(), source_document=_source_doc(), target_document=sbol2.Document())
    kinds = {item.missing_kind for item in result.missing_inputs}
    assert result.status == StageStatus.BLOCKED
    assert "restriction_enzyme" in kinds
    assert "ligase" in kinds


def test_default_options_block_for_sequence_edit_approval() -> None:
    stage = DomesticationStage(inventory=_inventory())
    result = stage.run(_request(), source_document=_source_doc(), target_document=sbol2.Document())
    assert result.status == StageStatus.BLOCKED
    assert result.required_approvals


def test_protocol_mode_requires_explicit_process_or_approval_id() -> None:
    options = BuildOptions()
    options.domestication.allow_sequence_domestication_edits = True
    options.protocol.mode = ProtocolMode.MANUAL
    stage = DomesticationStage(inventory=_inventory(), options=options)
    blocked = stage.run(_request(), source_document=_source_doc(), target_document=sbol2.Document())
    assert blocked.status == StageStatus.BLOCKED

    options.approvals.approved_processes.add("domestication_sequence_edit")
    stage2 = DomesticationStage(inventory=_inventory(), options=options)
    ok = stage2.run(_request(), source_document=_source_doc(), target_document=sbol2.Document())
    assert ok.status == StageStatus.SUCCESS
    assert ok.products[0].metadata["insert_identities"] == ["part"]
