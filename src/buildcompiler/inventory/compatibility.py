"""Deterministic compatibility route models and score ordering."""

from __future__ import annotations

from dataclasses import dataclass

from buildcompiler.domain import IndexedBackbone, IndexedPlasmid


@dataclass(frozen=True)
class RouteScore:
    missing_required_products: int = 0
    missing_domestications: int = 0
    missing_lvl1_plasmids: int = 0
    generated_or_planned_materials: int = 0
    lower_material_state_penalty: int = 0
    constraint_violations: int = 0
    total_assemblies: int = 0
    identity_tiebreak: tuple[str, ...] = ()

    def sort_key(self) -> tuple[int, int, int, int, int, int, int, tuple[str, ...]]:
        """Lower sort key is a better route."""
        return (
            self.constraint_violations,
            self.missing_required_products,
            self.missing_domestications,
            self.missing_lvl1_plasmids,
            self.generated_or_planned_materials,
            self.lower_material_state_penalty,
            self.total_assemblies,
            self.identity_tiebreak,
        )


@dataclass(frozen=True)
class Lvl1Route:
    request_id: str
    part_identities: tuple[str, ...]
    selected_part_plasmids: tuple[IndexedPlasmid, ...]
    missing_part_identities: tuple[str, ...]
    backbone: IndexedBackbone | None
    score: RouteScore


@dataclass(frozen=True)
class Lvl2Route:
    request_id: str
    region_order: tuple[str, ...]
    selected_lvl1_plasmids: tuple[IndexedPlasmid, ...]
    missing_region_identities: tuple[str, ...]
    backbone: IndexedBackbone | None
    score: RouteScore


@dataclass(frozen=True)
class RouteSelection:
    selected: Lvl1Route | Lvl2Route | None
    rejected: tuple[Lvl1Route | Lvl2Route, ...] = ()
