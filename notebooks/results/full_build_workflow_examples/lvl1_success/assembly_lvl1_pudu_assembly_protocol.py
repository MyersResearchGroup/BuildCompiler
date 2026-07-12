from pudu.assembly import SBOLLoopAssembly
from opentrons import protocol_api

assembly_data = [
    {
        "Product": "http://buildcompiler.org/standard_GFP_full_build/1",
        "Backbone": "https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/DVK_AE/1",
        "PartsList": [
            "https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/pJ23100_AB/1",
            "https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/pB0034_BC/1",
            "https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/pE0040_CD/1",
            "https://synbiohub.org/user/Gon/CIDARMoCloPlasmidsKit/pB0015_DE/1"
        ],
        "Restriction Enzyme": "https://synbiohub.org/user/Gon/Enzyme_Implementations/BsaI/1"
    }
]

metadata = {
    'protocolName': 'BuildCompiler assembly_lvl1 Assembly',
    'author': 'BuildCompiler',
    'apiLevel': '2.21',
}

def run(protocol: protocol_api.ProtocolContext):
    protocol_instance = SBOLLoopAssembly(assembly_data=assembly_data)
    protocol_instance.run(protocol)
