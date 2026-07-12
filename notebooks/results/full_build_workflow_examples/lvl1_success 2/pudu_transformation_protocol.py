from pudu.transformation import HeatShockTransformation
from opentrons import protocol_api

transformation_data = [
    {
        "Strain": "http://buildcompiler.org/E_coli_DH5alpha_with_standard_GFP_full_build/1",
        "Chassis": "E_coli_DH5alpha",
        "Plasmids": [
            "http://buildcompiler.org/standard_GFP_full_build/1"
        ]
    }
]

plasmid_locations = {
    "http://buildcompiler.org/standard_GFP_full_build/1": [
        "A1"
    ]
}

metadata = {
    'protocolName': 'BuildCompiler Transformation',
    'author': 'BuildCompiler',
    'apiLevel': '2.21',
}

def run(protocol: protocol_api.ProtocolContext):
    protocol_instance = HeatShockTransformation(
        transformation_data=transformation_data,
        plasmid_locations=plasmid_locations,
    )
    protocol_instance.run(protocol)
