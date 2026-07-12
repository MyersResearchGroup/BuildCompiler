from pudu.transformation import HeatShockTransformation
from opentrons import protocol_api

transformation_data = [
    {
        "Strain": "http://buildcompiler.org/domesticated_missing_promoter/1_strain",
        "Chassis": "E_coli_DH5alpha",
        "Plasmids": [
            "http://buildcompiler.org/domesticated_missing_promoter/1"
        ]
    },
    {
        "Strain": "http://buildcompiler.org/assembled_demo_tu/1_strain",
        "Chassis": "E_coli_DH5alpha",
        "Plasmids": [
            "http://buildcompiler.org/assembled_demo_tu/1"
        ]
    },
    {
        "Strain": "http://buildcompiler.org/assembled_demo_lvl2/1_strain",
        "Chassis": "E_coli_DH5alpha",
        "Plasmids": [
            "http://buildcompiler.org/assembled_demo_lvl2/1"
        ]
    }
]

plasmid_locations = {
    "http://buildcompiler.org/domesticated_missing_promoter/1": [
        "A1"
    ],
    "http://buildcompiler.org/assembled_demo_tu/1": [
        "B1"
    ],
    "http://buildcompiler.org/assembled_demo_lvl2/1": [
        "C1"
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
