import sbol2
from typing import Union
import zipfile
from .abstract_translator import translate_abstract_to_plasmids
from .sbol2build import golden_gate_assembly_plan
from .robotutils import assembly_plan_RDF_to_JSON, run_opentrons_script_with_json_to_zip

Plasmid = "Plasmid"  # Placeholder for the actual Plasmid class definition


class BuildCompiler:
    """Orchestrates the full build workflow for an SBOL design.

    This class owns the build state (indexed plasmids/backbones) and provides a
    high-level API to execute the full workflow: collection indexing, domestication,
    lvl1 and lvl2 assembly, transformation, and plating.

    :ivar design: SBOL design (ComponentDefinition, ModuleDefinition, or CombinatorialDerivation).
    :type design: sbol2.ComponentDefinition | sbol2.ModuleDefinition | sbol2.CombinatorialDerivation
    :ivar plasmids: Indexed plasmids linked to strains/collections.
    :type plasmids: list[Plasmid]
    """

    def __init__(self, abstract_design: Union[sbol2.ComponentDefinition, sbol2.ModuleDefinition, sbol2.CombinatorialDerivation], *,sbol_doc: sbol2.Document):
        self.abstract_design = abstract_design
        self.sbol_doc = sbol_doc
        self.collections = None
        self.indexed_plasmids = list[Plasmid]
        self.indexced_backbones = list[Plasmid]


    def index_collections(self, collections: list[sbol2.Collection]) -> dict[str, sbol2.Collection]:  
        """Index input collections into plasmids and backbones.

        Parses the provided collections (which may contain plasmids, backbones, or strains)
        and normalizes them into internal Plasmid/Backbone records that remain linked to
        their originating strain definitions.

        :param collections: Iterable of user-provided collections/documents.
        :type collections: Iterable
        :returns: None. Updates ``self.indexed_plasmids`` in place.
        :rtype: None
        :raises ValueError: If collection elements cannot be interpreted as plasmids.
        """
        self.collections = collections

        #TODO: Iterate thorugh the Collections and create a set of indexed plasmids, linking them to their originating definitions.
        # Updates indexed_plasmids 

  
        return "Success"
    
    def domestication(self,) -> list[sbol2.ComponentDefinition]:
        """Domesticate the indexed plasmids for Golden Gate assembly.

        For each indexed plasmid, this method identifies the necessary domestication
        steps (e.g., removing internal BsaI sites) and generates the corresponding
        domesticated sequences as new ComponentDefinitions in the SBOL document.

        :returns: List of domesticated ComponentDefinitions ready for assembly.
        :rtype: list[sbol2.ComponentDefinition]
        """

        #TODO: Check which parts from the abstract design are not present in the indexed plasmids with the appropiate fusion sites and need to be domesticated.
        #TODO: Create a SBOL representation of the domestication process, updating the SBOL Document.
        #TODO: Generate a protocol for the domestication process.
        protocol = "To be implemented by PUDU"
        #TODO: Updates indexed plasmids with domesticated versions.

        
        return protocol
    
    def assembly_lvl1(self,) -> list[sbol2.ComponentDefinition]:
        """Assemble level-1 plasmids for each gene/transcriptional unit.

        Uses indexed plasmids/backbones and the current design to assemble
        lvl1 plasmids in the correct order.

        :returns: List of assembled lvl1 plasmids.
        :rtype: list[Plasmid]
        :raises LookupError: If compatible plasmids or backbones cannot be found.
        """

        #TODO: Identify parts from the abstract design needed for lvl1 assembly and find compatible indexed plasmids/backbones.
        # if bacbckbone provided then use it.Then look for parts constraind by the backbone fusion sites.
        # else, run an algorithm to try a backbone from 4 the choices. If it fails on the 4 raise an error.
        #TODO: Create a SBOL representation of the assembly process, updating the SBOL Document.
        # Using he selected parts create the representation, you need Plasmids, BsaI and T4 Ligase.
        #TODO: Updates indexed plasmids with assembled versions.
        #TODO: Generate a protocol for the assembly process.
        protocol = "To be implemented by PUDU"

        return protocol
    
    def assembly_lvl2(self,) -> list[sbol2.ComponentDefinition]:
        """Assemble level-2 plasmids for the full design.

        Uses the assembled lvl1 plasmids and the current design to assemble
        lvl2 plasmids in the correct order.

        :returns: List of assembled lvl2 plasmids.
        :rtype: list[Plasmid]
        :raises LookupError: If compatible plasmids or backbones cannot be found.
        """ 

        #TODO: Identify parts from the abstract design needed for lvl2 assembly and find compatible indexed plasmids/backbones.
        #TODO: Create a SBOL representation of the assembly process, updating the SBOL Document.
        #TODO: Generate a protocol for the assembly process.
        protocol = "To be implemented by PUDU"
        #TODO: Updates indexed plasmids with assembled versions.

        return protocol
