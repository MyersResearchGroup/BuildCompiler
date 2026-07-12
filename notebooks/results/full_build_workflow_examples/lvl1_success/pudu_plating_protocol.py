from pudu.plating import Plating
from opentrons import protocol_api

plating_data = {
    "bacterium_locations": {
        "A1": "1_plated_A1_impl"
    }
}

metadata = {
    'protocolName': 'BuildCompiler Plating',
    'author': 'BuildCompiler',
    'apiLevel': '2.21',
}

def run(protocol: protocol_api.ProtocolContext):
    protocol_instance = Plating(plating_data=plating_data)
    protocol_instance.run(protocol)
