import sbol2
from typing import List

from buildcompiler.buildcompiler import Plasmid


def bacterial_transformation(
    plasmids: List[Plasmid],
    chassis_impl: sbol2.Implementation,
    chassis_md: sbol2.ModuleDefinition,  # TODO change to impl
    transformation_doc: sbol2.Document,
):
    for plasmid in plasmids:
        plasmid_impl = plasmid.plasmid_implementations[
            0
        ]  # TODO update with more sophisticated selection process?
        plasmid_cd = plasmid.plasmid_definition

        transformation_activity = sbol2.Activity(f"transform_{chassis_md.name}")
        transformation_activity.name = "Bacterial Tranformation"
        transformation_activity.types = "http://sbols.org/v2#build"

        chassis_usage = sbol2.Usage(
            uri=f"{chassis_md.name}_chassis",
            entity=chassis_impl.identity,
            role="http://sbols.org/v2#build",
        )

        plasmid_usage = sbol2.Usage(
            uri=f"{plasmid_cd.name}_plasmid_source",
            entity=plasmid_impl.identity,
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
        transformation_activity_plan.description = (  # TODO implement these for assembly activities as well
            "TODO: generate accurate description of transformation"
        )
        transformation_activity_association.plan = transformation_activity_plan

        transformation_activity_agent = sbol2.Agent("BuildCompiler")
        transformation_activity_association.agent = transformation_activity_agent

        transformation_activity.associations = [transformation_activity_association]

        new_strain_impl = sbol2.Implementation(f"{new_strain.displayId}_impl")

        new_strain_impl.built = new_strain.identity
        new_strain_impl.wasGeneratedBy = transformation_activity.identity

        transformation_doc.add_list(
            [
                new_strain_impl,
                transformation_activity,
                chassis_md,
                chassis_usage,
                chassis_module,
                new_strain,
                plasmid_functional_component,
                transformation_activity_plan,
            ]
        )
