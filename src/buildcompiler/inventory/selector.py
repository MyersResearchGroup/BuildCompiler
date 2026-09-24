"""Deterministic compatibility selector for lvl1/lvl2 route selection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import permutations, product
from typing import Any

from buildcompiler.api.options import BuildOptions
from buildcompiler.domain import BuildStage, MaterialState
from buildcompiler.inventory.compatibility import (
    Lvl1Route,
    Lvl2Route,
    RouteScore,
    RouteSelection,
)
from buildcompiler.inventory.inventory import Inventory


_STATE_RANK = {
    MaterialState.PLANNED: 0,
    MaterialState.GENERATED: 1,
    MaterialState.ASSEMBLED: 2,
    MaterialState.TRANSFORMED: 3,
    MaterialState.PLATED: 4,
}


class CompatibilitySelector:
    def __init__(
        self, inventory: Inventory, *, options: BuildOptions | None = None
    ) -> None:
        self.inventory = inventory
        self.options = options or BuildOptions()

    def _is_generated_or_planned(self, plasmid: Any) -> bool:
        source = (plasmid.metadata or {}).get("source", "")
        if source:
            return source in {"generated", "planned"}
        return plasmid.state in {MaterialState.PLANNED, MaterialState.GENERATED}

    def _constraint_filter(
        self, items: list[Any], constraints: Mapping[str, Any]
    ) -> list[Any]:
        allowed = set(constraints.get("allowed_identities", []))
        forbidden = set(constraints.get("forbidden_identities", []))
        antibiotic = constraints.get("antibiotic")
        out = []
        for item in items:
            if allowed and item.identity not in allowed:
                continue
            if item.identity in forbidden:
                continue
            if antibiotic and item.metadata.get("antibiotic") != antibiotic:
                continue
            out.append(item)
        return out

    def _best_candidate(
        self, candidates: list[Any], constraints: Mapping[str, Any]
    ) -> Any | None:
        filtered = self._constraint_filter(candidates, constraints)
        if not filtered:
            return None

        prefer_existing = self.options.selection.prefer_existing_collection_material
        prefer_state = self.options.selection.prefer_higher_material_state

        def _key(p: Any) -> tuple[int, int, str]:
            generated_penalty = int(
                prefer_existing and self._is_generated_or_planned(p)
            )
            state_penalty = -_STATE_RANK[p.state] if prefer_state else 0
            return (generated_penalty, state_penalty, p.identity)

        return sorted(filtered, key=_key)[0]

    def _candidate_key(self, candidate: Any) -> tuple[int, int, str]:
        prefer_existing = self.options.selection.prefer_existing_collection_material
        prefer_state = self.options.selection.prefer_higher_material_state
        generated_penalty = int(
            prefer_existing and self._is_generated_or_planned(candidate)
        )
        state_penalty = -_STATE_RANK[candidate.state] if prefer_state else 0
        return generated_penalty, state_penalty, candidate.identity

    def _fusion_sites(self, item: Any) -> tuple[str, ...]:
        return tuple((item.metadata or {}).get("fusion_sites", ()))

    def _chain_is_compatible(self, chain: Sequence[Any]) -> bool:
        annotated = [self._fusion_sites(item) for item in chain]
        if not annotated or not any(annotated):
            return True
        if any(len(sites) != 2 for sites in annotated):
            return False
        return all(left[1] == right[0] for left, right in zip(annotated, annotated[1:]))

    def _select_compatible_chain(
        self, candidate_groups: Sequence[list[Any]]
    ) -> tuple[Any, ...] | None:
        compatible = self._compatible_chains(candidate_groups)
        return compatible[0] if compatible else None

    def _compatible_chains(
        self, candidate_groups: Sequence[list[Any]]
    ) -> list[tuple[Any, ...]]:
        if not candidate_groups or any(not group for group in candidate_groups):
            return []
        compatible = [
            tuple(chain)
            for chain in product(*candidate_groups)
            if self._chain_is_compatible(chain)
        ]
        return sorted(
            compatible,
            key=lambda chain: tuple(self._candidate_key(item) for item in chain),
        )

    def _route_fusion_sites(self, selected: Sequence[Any]) -> tuple[str, str] | None:
        if not selected:
            return None
        first = self._fusion_sites(selected[0])
        last = self._fusion_sites(selected[-1])
        if len(first) == 2 and len(last) == 2:
            return first[0], last[1]
        return None

    def select_lvl1_route(
        self,
        *,
        request_id: str,
        part_identities: Sequence[str],
        constraints: Mapping[str, Any] | None = None,
    ) -> RouteSelection:
        active_constraints = constraints or {}
        candidate_groups: list[list[Any]] = []
        missing = []
        for part_identity in part_identities:
            candidates = self.inventory.find_single_part_plasmids(
                part_identity, antibiotic=active_constraints.get("antibiotic")
            )
            filtered = self._constraint_filter(candidates, active_constraints)
            candidate_groups.append(filtered)
            if not filtered:
                missing.append(part_identity)

        chains = self._compatible_chains(candidate_groups)
        requested_sites = (
            tuple(active_constraints["fusion_sites"])
            if "fusion_sites" in active_constraints
            else None
        )
        chain_backbones = [
            (
                chain,
                self.inventory.find_backbone(
                    fusion_sites=requested_sites or self._route_fusion_sites(chain),
                    antibiotic=active_constraints.get("antibiotic"),
                    stage=BuildStage.ASSEMBLY_LVL1,
                ),
            )
            for chain in chains
        ]
        feasible = [
            (chain, backbone) for chain, backbone in chain_backbones if backbone
        ]
        if feasible:
            chain, backbone = feasible[0]
        else:
            chain = chains[0] if chains else None
            backbone = None
        compatibility_violation = not missing and chain is None
        if compatibility_violation:
            selected: list[Any] = []
            missing = list(part_identities)
        else:
            selected = list(chain or ())

        score = RouteScore(
            missing_required_products=len(missing),
            missing_domestications=len(missing),
            generated_or_planned_materials=sum(
                1 for p in selected if self._is_generated_or_planned(p)
            ),
            lower_material_state_penalty=sum(
                (_STATE_RANK[MaterialState.PLATED] - _STATE_RANK[p.state])
                for p in selected
            )
            if self.options.selection.prefer_higher_material_state
            else 0,
            constraint_violations=int(compatibility_violation),
            identity_tiebreak=tuple(sorted(p.identity for p in selected))
            + tuple(missing),
        )
        route = Lvl1Route(
            request_id,
            tuple(part_identities),
            tuple(selected),
            tuple(missing),
            backbone,
            score,
        )
        return RouteSelection(selected=route, rejected=())

    def select_lvl2_route(
        self,
        *,
        request_id: str,
        region_identities: Sequence[str],
        constraints: Mapping[str, Any] | None = None,
    ) -> RouteSelection:
        active_constraints = constraints or {}
        max_regions = self.options.planning.lvl2_search.max_exhaustive_region_count
        allow_large = self.options.planning.lvl2_search.allow_large_order_search

        if "region_order" in active_constraints:
            constrained_order = tuple(active_constraints["region_order"])
            requested_regions = tuple(region_identities)
            if sorted(constrained_order) != sorted(requested_regions):
                blocked = Lvl2Route(
                    request_id=request_id,
                    region_order=constrained_order,
                    selected_lvl1_plasmids=(),
                    missing_region_identities=requested_regions,
                    backbone=None,
                    score=RouteScore(
                        missing_required_products=len(requested_regions),
                        missing_lvl1_plasmids=len(requested_regions),
                        constraint_violations=1,
                        identity_tiebreak=requested_regions,
                    ),
                )
                return RouteSelection(selected=None, rejected=(blocked,))
            orders = [constrained_order]
        elif len(region_identities) > max_regions and not allow_large:
            blocked = Lvl2Route(
                request_id=request_id,
                region_order=tuple(region_identities),
                selected_lvl1_plasmids=(),
                missing_region_identities=tuple(region_identities),
                backbone=None,
                score=RouteScore(
                    missing_required_products=len(region_identities),
                    missing_lvl1_plasmids=len(region_identities),
                    constraint_violations=1,
                    identity_tiebreak=tuple(region_identities),
                ),
            )
            return RouteSelection(selected=None, rejected=(blocked,))
        else:
            orders = sorted(set(permutations(region_identities)))

        routes = []
        for order in orders:
            candidate_groups: list[list[Any]] = []
            missing = []
            for region in order:
                candidates = self.inventory.find_lvl1_region_plasmids(region)
                filtered = self._constraint_filter(candidates, active_constraints)
                candidate_groups.append(filtered)
                if not filtered:
                    missing.append(region)
            chains = self._compatible_chains(candidate_groups)
            requested_sites = (
                tuple(active_constraints["fusion_sites"])
                if "fusion_sites" in active_constraints
                else None
            )
            chain_backbones = [
                (
                    candidate_chain,
                    self.inventory.find_backbone(
                        fusion_sites=requested_sites
                        or self._route_fusion_sites(candidate_chain),
                        antibiotic=active_constraints.get("antibiotic"),
                        stage=BuildStage.ASSEMBLY_LVL2,
                    ),
                )
                for candidate_chain in chains
            ]
            feasible = [
                (candidate_chain, candidate_backbone)
                for candidate_chain, candidate_backbone in chain_backbones
                if candidate_backbone
            ]
            if feasible:
                chain, backbone = feasible[0]
            else:
                chain = chains[0] if chains else None
                backbone = None
            compatibility_violation = not missing and chain is None
            if compatibility_violation:
                selected: list[Any] = []
                missing = list(order)
            else:
                selected = list(chain or ())
            score = RouteScore(
                missing_required_products=len(missing),
                missing_lvl1_plasmids=len(missing),
                generated_or_planned_materials=sum(
                    1 for p in selected if self._is_generated_or_planned(p)
                ),
                lower_material_state_penalty=sum(
                    (_STATE_RANK[MaterialState.PLATED] - _STATE_RANK[p.state])
                    for p in selected
                )
                if self.options.selection.prefer_higher_material_state
                else 0,
                total_assemblies=int(bool(missing)),
                constraint_violations=int(compatibility_violation),
                identity_tiebreak=tuple(p.identity for p in selected) + tuple(missing),
            )
            routes.append(
                Lvl2Route(
                    request_id,
                    tuple(order),
                    tuple(selected),
                    tuple(missing),
                    backbone,
                    score,
                )
            )

        ranked = sorted(routes, key=lambda r: r.score.sort_key())
        return RouteSelection(
            selected=ranked[0] if ranked else None, rejected=tuple(ranked[1:4])
        )
