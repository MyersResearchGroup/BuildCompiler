"""Normalized inventory facade with eager deterministic indexes."""

from __future__ import annotations

from collections import defaultdict

from buildcompiler.domain import (
    BuildStage,
    IndexedBackbone,
    IndexedPlasmid,
    IndexedReagent,
    MaterialState,
)


_MATERIAL_ORDER = {
    MaterialState.PLANNED: 0,
    MaterialState.GENERATED: 1,
    MaterialState.ASSEMBLED: 2,
    MaterialState.TRANSFORMED: 3,
    MaterialState.PLATED: 4,
}


class Inventory:
    def __init__(
        self,
        *,
        plasmids: list[IndexedPlasmid] | None = None,
        backbones: list[IndexedBackbone] | None = None,
        reagents: list[IndexedReagent] | None = None,
    ) -> None:
        self.plasmids_by_identity: dict[str, IndexedPlasmid] = {}
        self.plasmids_by_insert_identity: dict[str, list[IndexedPlasmid]] = defaultdict(
            list
        )
        self.plasmids_by_fusion_sites: dict[tuple[str, ...], list[IndexedPlasmid]] = (
            defaultdict(list)
        )
        self.plasmids_by_antibiotic: dict[str, list[IndexedPlasmid]] = defaultdict(list)

        self.backbones_by_identity: dict[str, IndexedBackbone] = {}
        self.backbones_by_fusion_sites_and_antibiotic: dict[
            tuple[tuple[str, ...], str], list[IndexedBackbone]
        ] = defaultdict(list)

        self.reagents_by_identity: dict[str, IndexedReagent] = {}
        self.reagents_by_name: dict[str, IndexedReagent] = {}

        self.generated_products_by_identity: dict[str, IndexedPlasmid] = {}

        for plasmid in plasmids or []:
            self._add_plasmid(plasmid)
        for backbone in backbones or []:
            self._add_backbone(backbone)
        for reagent in reagents or []:
            self._add_reagent(reagent)

    def _sorted_plasmids(self, items: list[IndexedPlasmid]) -> list[IndexedPlasmid]:
        return sorted(items, key=lambda p: p.identity)

    def _backbone_stage(self, backbone: IndexedBackbone) -> BuildStage | None:
        raw = backbone.metadata.get("stage") if backbone.metadata else None
        if raw is None:
            return None
        if isinstance(raw, BuildStage):
            return raw
        try:
            return BuildStage(raw)
        except ValueError:
            return None

    def _remove_plasmid_from_secondary_indexes(self, plasmid: IndexedPlasmid) -> None:
        for insert_identity in sorted(plasmid.metadata.get("insert_identities", [])):
            existing = self.plasmids_by_insert_identity.get(insert_identity, [])
            filtered = [
                indexed for indexed in existing if indexed.identity != plasmid.identity
            ]
            if filtered:
                self.plasmids_by_insert_identity[insert_identity] = filtered
            else:
                self.plasmids_by_insert_identity.pop(insert_identity, None)

        fusion_sites = tuple(plasmid.metadata.get("fusion_sites", ()))
        if fusion_sites:
            existing = self.plasmids_by_fusion_sites.get(fusion_sites, [])
            filtered = [
                indexed for indexed in existing if indexed.identity != plasmid.identity
            ]
            if filtered:
                self.plasmids_by_fusion_sites[fusion_sites] = filtered
            else:
                self.plasmids_by_fusion_sites.pop(fusion_sites, None)

        antibiotic = plasmid.metadata.get("antibiotic")
        if antibiotic:
            existing = self.plasmids_by_antibiotic.get(antibiotic, [])
            filtered = [
                indexed for indexed in existing if indexed.identity != plasmid.identity
            ]
            if filtered:
                self.plasmids_by_antibiotic[antibiotic] = filtered
            else:
                self.plasmids_by_antibiotic.pop(antibiotic, None)

    def _add_plasmid(self, plasmid: IndexedPlasmid) -> None:
        existing = self.plasmids_by_identity.get(plasmid.identity)
        if existing is not None:
            self._remove_plasmid_from_secondary_indexes(existing)

        self.plasmids_by_identity[plasmid.identity] = plasmid
        for insert_identity in sorted(plasmid.metadata.get("insert_identities", [])):
            self.plasmids_by_insert_identity[insert_identity].append(plasmid)
            self.plasmids_by_insert_identity[insert_identity] = self._sorted_plasmids(
                self.plasmids_by_insert_identity[insert_identity]
            )

        fusion_sites = tuple(plasmid.metadata.get("fusion_sites", ()))
        if fusion_sites:
            self.plasmids_by_fusion_sites[fusion_sites].append(plasmid)
            self.plasmids_by_fusion_sites[fusion_sites] = self._sorted_plasmids(
                self.plasmids_by_fusion_sites[fusion_sites]
            )

        antibiotic = plasmid.metadata.get("antibiotic")
        if antibiotic:
            self.plasmids_by_antibiotic[antibiotic].append(plasmid)
            self.plasmids_by_antibiotic[antibiotic] = self._sorted_plasmids(
                self.plasmids_by_antibiotic[antibiotic]
            )

    def _add_backbone(self, backbone: IndexedBackbone) -> None:
        self.backbones_by_identity[backbone.identity] = backbone
        fusion_sites = tuple(backbone.metadata.get("fusion_sites", ()))
        antibiotic = backbone.metadata.get("antibiotic")
        if fusion_sites and antibiotic:
            key = (fusion_sites, antibiotic)
            self.backbones_by_fusion_sites_and_antibiotic[key].append(backbone)
            self.backbones_by_fusion_sites_and_antibiotic[key] = sorted(
                self.backbones_by_fusion_sites_and_antibiotic[key],
                key=lambda b: b.identity,
            )

    def _add_reagent(self, reagent: IndexedReagent) -> None:
        self.reagents_by_identity[reagent.identity] = reagent
        if reagent.name:
            self.reagents_by_name[reagent.name] = reagent

    def find_single_part_plasmids(
        self, part_identity: str, *, antibiotic: str | None = None
    ) -> list[IndexedPlasmid]:
        matches = list(self.plasmids_by_insert_identity.get(part_identity, []))
        if antibiotic is not None:
            matches = [p for p in matches if p.metadata.get("antibiotic") == antibiotic]
        return self._sorted_plasmids(matches)

    def find_lvl1_region_plasmids(
        self,
        region_identity: str,
        *,
        min_material_state: MaterialState = MaterialState.PLANNED,
    ) -> list[IndexedPlasmid]:
        matches = self.plasmids_by_insert_identity.get(region_identity, [])
        min_rank = _MATERIAL_ORDER[min_material_state]
        filtered = [p for p in matches if _MATERIAL_ORDER[p.state] >= min_rank]
        return self._sorted_plasmids(filtered)

    def find_backbone(
        self,
        *,
        fusion_sites: tuple[str, ...] | None = None,
        antibiotic: str | None = None,
        stage: BuildStage | None = None,
    ) -> IndexedBackbone | None:
        if fusion_sites is not None and antibiotic is not None:
            candidates = list(
                self.backbones_by_fusion_sites_and_antibiotic.get(
                    (tuple(fusion_sites), antibiotic), []
                )
            )
        else:
            candidates = sorted(
                self.backbones_by_identity.values(), key=lambda b: b.identity
            )
            if fusion_sites is not None:
                candidates = [
                    b
                    for b in candidates
                    if tuple(b.metadata.get("fusion_sites", ())) == tuple(fusion_sites)
                ]
            if antibiotic is not None:
                candidates = [
                    b for b in candidates if b.metadata.get("antibiotic") == antibiotic
                ]
        if stage is not None:
            candidates = [b for b in candidates if self._backbone_stage(b) == stage]
        return candidates[0] if candidates else None

    def find_restriction_enzyme(self, name: str) -> IndexedReagent | None:
        reagent = self.reagents_by_name.get(name)
        if reagent and reagent.reagent_type == "restriction_enzyme":
            return reagent
        return None

    def find_ligase(self, preferred: str | None = None) -> IndexedReagent | None:
        if preferred:
            reagent = self.reagents_by_name.get(preferred)
            if reagent and reagent.reagent_type == "ligase":
                return reagent
        ligases = sorted(
            (
                r
                for r in self.reagents_by_identity.values()
                if r.reagent_type == "ligase"
            ),
            key=lambda r: r.identity,
        )
        return ligases[0] if ligases else None

    def add_generated_product(self, product: IndexedPlasmid) -> None:
        self.generated_products_by_identity[product.identity] = product
        self._add_plasmid(product)
