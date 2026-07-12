from pudu.assembly import SBOLLoopAssembly
from opentrons import protocol_api

assembly_data = [
    {
        "Product": "http://buildcompiler.org/assembled_demo_lvl2/1",
        "Backbone": "demo_lvl2_backbone",
        "PartsList": [
            "http://buildcompiler.org/assembled_demo_tu/1"
        ],
        "Restriction Enzyme": "BbsI"
    }
]

metadata = {
    'protocolName': 'BuildCompiler assembly_lvl2 Assembly',
    'author': 'BuildCompiler',
    'apiLevel': '2.21',
}

def run(protocol: protocol_api.ProtocolContext):
    protocol_instance = SBOLLoopAssembly(assembly_data=assembly_data)
    protocol_instance.run(protocol)
