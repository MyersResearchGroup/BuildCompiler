from pudu.assembly import SBOLLoopAssembly
from opentrons import protocol_api

assembly_data = [
    {
        "Product": "http://buildcompiler.org/domesticated_missing_promoter/1",
        "Backbone": "demo_domestication_backbone",
        "PartsList": [
            "http://buildcompiler.org/missing_promoter/1"
        ],
        "Restriction Enzyme": "BsaI"
    }
]

metadata = {
    'protocolName': 'BuildCompiler domestication Assembly',
    'author': 'BuildCompiler',
    'apiLevel': '2.21',
}

def run(protocol: protocol_api.ProtocolContext):
    protocol_instance = SBOLLoopAssembly(assembly_data=assembly_data)
    protocol_instance.run(protocol)
