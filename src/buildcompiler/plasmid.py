from typing import List

import sbol2
import re

from buildcompiler.abstract_translator import extract_fusion_sites
from buildcompiler.constants import ANTIBIOTIC_MAP, ANTIBIOTIC_RESISTANCE, FUSION_SITES


class Plasmid:
    def __init__(
        self,
        definition: sbol2.ComponentDefinition,
        strain_definition: sbol2.ModuleDefinition,
        plasmid_implementations: List[sbol2.Implementation],
        strain_implementations: List[sbol2.Implementation],
        doc: sbol2.document,
    ):
        self.plasmid_definition = definition
        self.strain_definitions = [strain_definition]
        self.plasmid_implementations = plasmid_implementations
        self.strain_implementations = strain_implementations
        self.fusion_sites = self._match_fusion_sites(doc)
        self.name = definition.displayId + "".join(f"_{s}" for s in self.fusion_sites)
        self.antibiotic_resistance = self._get_antibiotic_resistance(doc)

    def _match_fusion_sites(self, doc: sbol2.document) -> List[str]:
        fusion_site_definitions = extract_fusion_sites(self.plasmid_definition, doc)
        fusion_sites = []
        for site in fusion_site_definitions:
            sequence_obj = doc.getSequence(site.sequences[0])
            sequence = sequence_obj.elements

            for key, seq in FUSION_SITES.items():
                if seq == sequence.upper():
                    fusion_sites.append(key)

        return [fusion_sites[0], fusion_sites[-1]]

    def _get_antibiotic_resistance(self, doc: sbol2.Document) -> str:
        for component in (
            self.plasmid_definition.components
        ):  # go a level deeper, within the backbone core component
            definition = doc.get(component.definition)
            for subcomponent in definition.components:
                subcomponent_def = doc.get(subcomponent.definition)
                if ANTIBIOTIC_RESISTANCE in subcomponent_def.roles:
                    match = re.search(
                        r"\b(" + "|".join(ANTIBIOTIC_MAP) + r")_",
                        subcomponent_def.displayId,
                        re.IGNORECASE,
                    )
                    if match:
                        return ANTIBIOTIC_MAP[match.group(1).lower()]
                    return "Unknown"

        return None

    def __repr__(self) -> str:
        strain_ids = (
            [getattr(s, "identity", None) for s in self.strain_definitions]
            if self.strain_definitions
            else []
        )

        plasmid_impl_ids = (
            [getattr(p, "identity", None) for p in self.plasmid_implementations]
            if self.plasmid_implementations
            else []
        )

        strain_impl_ids = (
            [getattr(s, "identity", None) for s in self.strain_implementations]
            if self.strain_implementations
            else []
        )

        return (
            f"Plasmid:\n"
            f"  Name: {self.name}\n"
            f"  Plasmid Definition: {getattr(self.plasmid_definition, 'identity', 'None')}\n"
            f"  Strain Definitions: {strain_ids}\n"
            f"  Plasmid Implementations: {plasmid_impl_ids or 'None'}\n"
            f"  Strain Implementations: {strain_impl_ids or 'None'}\n"
            f"  Fusion Sites: {self.fusion_sites or 'Not found'}\n"
            f"  Antibiotic Resistance: {self.antibiotic_resistance or 'None'}\n"
        )

    def __eq__(self, other):
        if not isinstance(other, Plasmid):
            return False
        return self.plasmid_definition == other.plasmid_definition

    def __hash__(self):
        return hash(self.plasmid_definition)
