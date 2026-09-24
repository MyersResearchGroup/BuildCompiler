"""Immutable protocol inputs shared by build stages and protocol compilers."""

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterialRef:
    """Stable material identity with a separate human-readable label."""

    identity: str
    label: str

    def __post_init__(self) -> None:
        if not self.identity or not self.label:
            raise ValueError("Material identity and label must be nonempty.")

    @classmethod
    def from_identity(cls, identity: str, label: str | None = None) -> "MaterialRef":
        """Keep the full identity and derive a display label when none is supplied."""
        if not isinstance(identity, str) or not identity:
            raise ValueError("Material identities must be nonempty strings.")
        if label is None:
            segments = [part for part in urlsplit(identity).path.split("/") if part]
            # Treat a trailing numeric path segment as an SBOL version for display.
            label = (
                segments[-2]
                if len(segments) > 1 and segments[-1].isdigit()
                else (segments[-1] if segments else identity)
            )
        return cls(identity=identity, label=label)


@dataclass(frozen=True, slots=True, kw_only=True)
class AssemblyReaction:
    """A product and the ordered components needed for one assembly."""

    id: str
    product: MaterialRef
    backbone: MaterialRef
    parts: tuple[MaterialRef, ...]
    restriction_enzyme: MaterialRef

    def __post_init__(self) -> None:
        if not self.id or not self.parts:
            raise ValueError("An assembly reaction requires an id and ordered parts.")
        if not isinstance(self.parts, tuple):
            raise TypeError("AssemblyReaction.parts must be a tuple.")


@dataclass(frozen=True, slots=True, kw_only=True)
class AssemblyRequest:
    """An ordered batch of assembly reactions from one build stage."""

    id: str
    reactions: tuple[AssemblyReaction, ...]
    source_stage_id: str | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.reactions:
            raise ValueError("An assembly request requires an id and reactions.")
        if not isinstance(self.reactions, tuple):
            raise TypeError("AssemblyRequest.reactions must be a tuple.")
        if len({reaction.id for reaction in self.reactions}) != len(self.reactions):
            raise ValueError("Reaction ids must be unique within a request.")


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformationReaction:
    """A target strain, its chassis and ordered input plasmids."""

    id: str
    strain: MaterialRef
    chassis: MaterialRef
    plasmids: tuple[MaterialRef, ...]

    def __post_init__(self) -> None:
        if not self.id or not self.plasmids:
            raise ValueError("A transformation requires an id and plasmids.")
        if not isinstance(self.plasmids, tuple):
            raise TypeError("Transformation plasmids must be a tuple.")


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformationRequest:
    """An ordered batch of strain transformations from one build stage."""

    id: str
    reactions: tuple[TransformationReaction, ...]
    source_stage_id: str | None = None

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.reactions, tuple) or not self.reactions:
            raise ValueError(
                "A transformation request requires an id and a nonempty reaction tuple."
            )
        if len({r.id for r in self.reactions}) != len(self.reactions):
            raise ValueError("Reaction ids must be unique within a request.")


@dataclass(frozen=True, slots=True, kw_only=True)
class PlatingRequest:
    """The exact upstream sample IDs selected for dilution and plating."""

    id: str
    sample_ids: tuple[str, ...]
    source_stage_id: str | None = None

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.sample_ids, tuple) or not self.sample_ids:
            raise ValueError(
                "A plating request requires an id and a nonempty sample tuple."
            )
        if len(set(self.sample_ids)) != len(self.sample_ids):
            raise ValueError("Plating source sample ids must be unique.")


ProtocolRequest = AssemblyRequest | TransformationRequest | PlatingRequest
