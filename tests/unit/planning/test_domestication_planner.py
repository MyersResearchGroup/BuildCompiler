import sbol2
import pytest

from buildcompiler.constants import PART_ROLES
from buildcompiler.planning import (
    DomesticationPlanner,
    select_deterministic_flanking_sequence,
)


def _part(identity: str, role: str, sequence: str | None = None) -> sbol2.ComponentDefinition:
    doc = sbol2.Document()
    part = sbol2.ComponentDefinition(identity)
    part.roles = role
    doc.addComponentDefinition(part)
    if sequence is not None:
        seq = sbol2.Sequence(f"{identity}_seq")
        seq.elements = sequence
        seq.encoding = sbol2.SBOL_ENCODING_IUPAC
        doc.addSequence(seq)
        part.sequences = seq.identity
    return part


def test_supported_role_produces_plan() -> None:
    planner = DomesticationPlanner()
    part = _part("https://example.org/p", sorted(PART_ROLES)[0], "ATGCGT")
    plan = planner.plan(part)
    assert plan.part_identity == part.identity
    assert plan.part_role in {"promoter", "rbs", "cds", "terminator"}


def test_unsupported_role_fails_structurally() -> None:
    planner = DomesticationPlanner()
    part = _part("https://example.org/x", "https://example.org/unsupported", "ATGC")
    with pytest.raises(ValueError, match="Unsupported domestication role"):
        planner.plan(part)


def test_missing_sequence_fails() -> None:
    planner = DomesticationPlanner()
    part = _part("https://example.org/p2", sorted(PART_ROLES)[0])
    with pytest.raises(ValueError, match="missing a usable DNA sequence"):
        planner.plan(part)


def test_bsai_sites_create_edit_proposals_without_mutating_sequence() -> None:
    planner = DomesticationPlanner()
    original = "AAAGGTCTCTTT"
    part = _part("https://example.org/p3", sorted(PART_ROLES)[0], original)
    plan = planner.plan(part)
    assert len(plan.sequence_edit_proposals) == 1
    assert plan.sequence_edit_proposals[0].site_sequence == "GGTCTC"
    seq = part.doc.find(part.sequences[0])
    assert seq.elements == original


def test_deterministic_flanking_sequence_is_explicit_todo() -> None:
    with pytest.raises(NotImplementedError, match="planned TODO"):
        select_deterministic_flanking_sequence(
            source_sequence="ATGC",
            flank_length=35,
        )
