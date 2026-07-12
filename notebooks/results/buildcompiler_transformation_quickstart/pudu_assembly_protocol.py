from pudu.assembly import SBOLLoopAssembly
from opentrons import protocol_api


# Protocol data
assembly_data = [
    {
        'Product': 'http://buildcompiler.org/standard_GFP_transformation_lvl1/1',
        'Backbone': 'https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/DVK_AE/1',
        'PartsList': [
            'https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/pJ23100_AB/1',
            'https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/pB0034_BC/1',
            'https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/pE0040_CD/1',
            'https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/pB0015_DE/1'
        ],
        'Restriction Enzyme': 'https://synbiohub.org/user/Gon/Enzyme_Implementations/BsaI/1'
    }
]

# Protocol metadata
metadata = {
    'protocolName': 'BuildCompiler Level-1 Assembly',
    'author': 'BuildCompiler',
    'description': 'PUDU assembly generated from BuildCompiler level-1 input.',
    'apiLevel': '2.21'
}


def run(protocol: protocol_api.ProtocolContext):
    """Main protocol execution function"""

    protocol_instance = SBOLLoopAssembly(assembly_data=assembly_data)
    protocol_instance.run(protocol)



# ======================================================================
# PARAMETER REFERENCE — SBOLLoopAssembly
#
# To customize your protocol, add any of the parameters below
# to the SBOLLoopAssembly() constructor call in run() above.
# Example:  protocol_instance = SBOLLoopAssembly(
#               assembly_data=assembly_data,
#               replicates=3,
#               initial_tip='B1',
#           )
# ======================================================================
#
# [SBOLLoopAssembly]
#   assembly_data                Optional  = None
#   json_params                  Optional  = None
#   assemblies                   Optional  = None
#
# [BaseAssembly]
#   volume_total_reaction        float     = 20
#   volume_part                  float     = 2
#   volume_restriction_enzyme    float     = 2
#   volume_t4_dna_ligase         float     = 4
#   volume_t4_dna_ligase_buffer  float     = 2
#   replicates                   int       = 1
#   thermocycler_starting_well   int       = 0
#   thermocycler_labware         str       = nest_96_wellplate_100ul_pcr_full_skirt
#   temperature_module_labware   str       = opentrons_24_aluminumblock_nest_1.5ml_snapcap
#   temperature_module_position  str       = 1
#   tiprack_labware              str       = opentrons_96_tiprack_20ul
#   tiprack_positions            Optional  = None
#   pipette                      str       = p20_single_gen2
#   pipette_position             str       = left
#   initial_tip                  Optional  = None
#   aspiration_rate              float     = 0.5
#   dispense_rate                float     = 1
#   take_picture                 bool      = False
#   take_video                   bool      = False
#   water_testing                bool      = False
#   output_xlsx                  bool      = True
#   protocol_name                str       = 
#
# ----------------------------------------------------------------------
# Full parameter descriptions:
#
# [SBOLLoopAssembly]
# SBOL Loop Assembly - handles explicit assembly dictionaries from SBOL format.
# Each assembly dictionary represents one specific construct to build.
#
# [BaseAssembly]
# Abstract base class for Loop Assembly protocols.
# Contains shared hardware setup, liquid handling, and tip management functionality.
#
# [ABC]
# Helper class that provides a standard way to create an ABC using
# inheritance.