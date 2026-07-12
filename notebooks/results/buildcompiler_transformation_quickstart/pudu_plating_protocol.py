from pudu.plating import Plating
from opentrons import protocol_api


# Protocol data
plating_data = {
    'bacterium_locations': {
        'A1': [
            'E_coli_DH5alpha_with_standard_GFP_transformation_lvl1',
            'Competent_Cell_DH5alpha',
            'standard_GFP_transformation_lvl1',
            'Media_1'
        ],
        'B1': [
            'E_coli_DH5alpha_with_standard_GFP_transformation_lvl1',
            'Competent_Cell_DH5alpha',
            'standard_GFP_transformation_lvl1',
            'Media_1'
        ]
    }
}

# Protocol metadata
metadata = {
    'protocolName': 'BuildCompiler Plating',
    'author': 'BuildCompiler',
    'description': 'PUDU plating generated from BuildCompiler transformation output.',
    'apiLevel': '2.21'
}


def run(protocol: protocol_api.ProtocolContext):
    """Main protocol execution function"""

    protocol_instance = Plating(plating_data=plating_data)
    protocol_instance.run(protocol)



# ======================================================================
# PARAMETER REFERENCE — Plating
#
# To customize your protocol, add any of the parameters below
# to the Plating() constructor call in run() above.
# Example:  protocol_instance = Plating(
#               plating_data=plating_data,
#               replicates=3,
#               initial_tip='B1',
#           )
# ======================================================================
#
# [Plating]
#   plating_data                Optional  = None
#   json_params                 Optional  = None
#   volume_total_reaction       float     = 20
#   volume_bacteria_transfer    float     = 2
#   volume_colony               float     = 4
#   dilution_factor             float     = 10
#   volume_lb                   float     = 10000
#   replicates                  int       = 1
#   number_dilutions            int       = 2
#   max_colonies                int       = 192
#   thermocycler_starting_well  int       = 0
#   thermocycler_labware        str       = biorad_96_wellplate_200ul_pcr
#   small_tiprack               str       = opentrons_96_filtertiprack_20ul
#   small_tiprack_position      str       = 9
#   initial_small_tip           Optional  = None
#   large_tiprack               str       = opentrons_96_filtertiprack_200ul
#   large_tiprack_position      str       = 1
#   initial_large_tip           Optional  = None
#   small_pipette               str       = p20_single_gen2
#   small_pipette_position      str       = left
#   large_pipette               str       = p300_single_gen2
#   large_pipette_position      str       = right
#   dilution_plate              str       = nest_96_wellplate_100ul_pcr_full_skirt
#   dilution_plate_position1    str       = 2
#   dilution_plate_position2    str       = 3
#   agar_plate                  str       = nest_96_wellplate_100ul_pcr_full_skirt
#   agar_plate_position1        str       = 5
#   agar_plate_position2        str       = 6
#   tube_rack                   str       = opentrons_15_tuberack_falcon_15ml_conical
#   tube_rack_position          str       = 4
#   lb_tube_position            int       = 0
#   aspiration_rate             float     = 0.5
#   dispense_rate               float     = 1
#   bacterium_locations         Optional  = None
#   protocol_name               str       = plating_layout
#
# ----------------------------------------------------------------------
# Full parameter descriptions:
#
# [Plating]
# Automated serial-dilution and spot-plating protocol for the Opentrons OT-2.
#
# Takes transformed bacteria from a thermocycler plate, performs up to two
# sequential 10× (or custom) dilutions in a dilution plate, and spots each
# dilution onto an agar plate. Supports multiple replicates and automatically
# distributes across two physical plates when colony counts exceed 96.
#
# After simulation, writes a JSON and an Excel file mapping each agar-plate
# well to the construct name, dilution ratio, and replicate number.
#
# Attributes:
#     volume_total_reaction: Volume of bacteria loaded in each thermocycler
#         source well, in µL. Used for liquid-tracking display only.
#     volume_bacteria_transfer: Volume transferred from each source well into
#         the dilution well, in µL.
#     volume_colony: Volume spotted from each dilution well onto the agar
#         plate per replicate, in µL.
#     dilution_factor: Serial dilution factor applied at each step (e.g. 10
#         for a 1:10 dilution). The LB volume pre-loaded into each dilution
#         well is ``volume_bacteria_transfer × (dilution_factor − 1)``.
#     volume_lb: Total LB volume in the stock tube, in µL. Used for liquid
#         tracking on the Opentrons deck visualiser.
#     replicates: Number of agar spots per construct per dilution step.
#     number_dilutions: Number of serial dilution steps to perform (max 2).
#     number_constructs: Number of unique constructs derived from
#         ``bacterium_locations``.
#     total_colonies: Total agar wells that will be plated
#         (``number_constructs × number_dilutions × replicates``).
#     max_colonies: Hard cap on ``total_colonies``; raises ``ValueError``
#         if exceeded.
#     bacterium_locations: Dict mapping thermocycler well names to construct
#         identifiers, e.g. ``{'A1': 'GFP_construct', 'B1': ['RFP', 'v2']}``.
#     protocol_name: Base name for output files (JSON and Excel).