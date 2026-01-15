import sbol2
from typing import List
from .abstract_translator import extract_toplevel_definition


def bacterial_transformation(
    transformation_doc: sbol2.Document,
    chassis_doc: sbol2.Document,
    plasmid_docs: List[sbol2.Document],
    transformation_mach: str,
    protocol: str,
    params: str,
) -> sbol2.Document:
    # TODO add params to encode information about protocol, machine information into transformation activity/plan
    chassis_md = chassis_doc.moduleDefinitions[0]

    for plasmid_doc in plasmid_docs:
        plasmid_cd = extract_toplevel_definition(plasmid_doc)

        transformation_activity = sbol2.Activity(f"transform_{chassis_md.name}")
        transformation_activity.name = "Bacterial Tranformation"
        transformation_activity.types = "http://sbols.org/v2#build"

        chassis_usage = sbol2.Usage(
            uri=f"{chassis_md.name}_chassis_source",
            entity=chassis_md.identity,
            role="http://sbols.org/v2#build",
        )

        plasmid_usage = sbol2.Usage(
            uri=f"{plasmid_cd.name}_plasmid_source",
            entity=plasmid_cd.identity,
            role="http://sbols.org/v2#build",
        )

        transformation_activity.usages = [chassis_usage, plasmid_usage]

        new_strain = sbol2.ModuleDefinition(f"{chassis_md.name}_with_{plasmid_cd.name}")
        chassis_module = sbol2.Module(uri=f"{chassis_md.name}_chassis")
        chassis_module.definition = chassis_md.identity
        plasmid_functional_component = sbol2.FunctionalComponent(
            uri=f"{plasmid_cd.name}_engineered_plasmid"
        )
        plasmid_functional_component.definition = plasmid_cd.identity

        new_strain.modules = [chassis_module]
        new_strain.functionalComponents = [plasmid_functional_component]

        transformation_activity_association = sbol2.Association(
            f"transform_{chassis_md.name}_association"
        )

        transformation_activity_plan = sbol2.Plan(
            f"{new_strain.displayId}_transformation_plan"
        )
        transformation_activity_plan.description = (
            "TODO: generate accurate description of transformation"
        )
        transformation_activity_association.plan = transformation_activity_plan

        transformation_activity_agent = sbol2.Agent("BuildCompiler")
        transformation_activity_association.agent = transformation_activity_agent

        transformation_activity.associations = [transformation_activity_association]

        new_strain.wasGeneratedBy = transformation_activity
        new_strain.roles = ["http://purl.obolibrary.org/obo/NCIT_C14419"]

        transformation_doc.add_list(
            [
                transformation_activity,
                chassis_md,
                chassis_usage,
                chassis_module,
                new_strain,
                plasmid_functional_component,
                transformation_activity_plan,
            ]
        )

    return transformation_doc
