import sbol2
from typing import Union, List
import zipfile
from abstract_translator import translate_abstract_to_plasmids
from sbol2build import golden_gate_assembly_plan
from robotutils import assembly_plan_RDF_to_JSON, run_opentrons_script_with_json_to_zip


# function which input is an abstract design and  output build specifications by creating an assembly plan, and a zip file with a run_sbol2assembly.py, an automated_assembly_log.txt, assemblyplan_output.JSON, and assembly_protocol.xlsx

def assembly_compiler(abstract_design: Union[sbol2.Component, sbol2.CombinatorialDerivation], 
                        plasmid_collection: str,
                        plasmid_acceptor_backbone: sbol2.Document,
                        document: sbol2.Document,
                        files_path: str) -> zipfile.ZipFile:
    """
    Compiles an abstract design into build specifications.
    
    Args:
        abstract_design (Union[sbol2.Component, sbol2.CombinatorialDerivation]): The abstract design to be compiled.
        specifications (sbol2.Component): The component to store the build specifications.
    Returns:
        zipfile.ZipFile: A zip file containing the build specifications and assembly plan.
    """
    restriction_enzyme = "BsaI"
    # Translate abstract design to plasmids
    list_of_plasmids = translate_abstract_to_plasmids(abstract_design_doc = abstract_design,
                                                      plasmid_collection = plasmid_collection,
                                                      backbone_doc= plasmid_acceptor_backbone)       
    


    # Create assembly plan
    assembly_plan = golden_gate_assembly_plan(name = "Assembly_Plan",
                                              parts_in_backbone= list_of_plasmids,
                                              plasmid_acceptor_backbone= plasmid_acceptor_backbone,
                                              restriction_enzyme= restriction_enzyme,
                                              document= document)
    
    # Generate build specifications JSON
    build_specs_JSON = assembly_plan_RDF_to_JSON(assembly_plan)
    
    # Create zip file with required files
    zip_file = run_opentrons_script_with_json_to_zip(opentrons_script_path= files_path + "/run_sbol2assembly_libre.py",
                                                     json_file_path= files_path + "/assemblyplan_output.json",
                                                     zip_name= "buildcompiler.zip",
                                                     overwrite= True)

    return assembly_plan, zip_file