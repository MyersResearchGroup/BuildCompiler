import json
import argparse
from pathlib import Path


DEFAULT_REACTION = {
    "total": 20,
    "part": 2,
    "restriction_enzyme": 2,
    "t4_ligase": 4,
    "t4_ligase_buffer": 2,
}


def _name_from_uri(value):
    if not value:
        return "Unknown"
    parts = str(value).rstrip("/").split("/")
    if len(parts) >= 2 and parts[-1].isdigit():
        return parts[-2]
    return parts[-1]


def _validate_assembly(assembly, index):
    required = {"Product", "Backbone", "PartsList", "Restriction Enzyme"}
    missing = sorted(required - set(assembly))
    if missing:
        raise ValueError(f"Assembly {index} is missing required field(s): {', '.join(missing)}")
    if not isinstance(assembly["PartsList"], list) or not assembly["PartsList"]:
        raise ValueError(f"Assembly {index} must include at least one part in PartsList")


def _reaction_rows(assembly):
    backbone = _name_from_uri(assembly["Backbone"])
    enzyme = _name_from_uri(assembly["Restriction Enzyme"])
    parts = [_name_from_uri(part) for part in assembly["PartsList"]]
    dna_inputs = [backbone] + parts

    reagents_volume = (
        DEFAULT_REACTION["restriction_enzyme"]
        + DEFAULT_REACTION["t4_ligase"]
        + DEFAULT_REACTION["t4_ligase_buffer"]
    )
    dna_volume = len(dna_inputs) * DEFAULT_REACTION["part"]
    water_volume = DEFAULT_REACTION["total"] - reagents_volume - dna_volume

    if water_volume < 0:
        raise ValueError(
            f"Reaction for {_name_from_uri(assembly['Product'])} needs {-water_volume} uL more than "
            f"the configured {DEFAULT_REACTION['total']} uL total volume."
        )

    rows = [
        ("Nuclease-free water", water_volume),
        ("T4 DNA ligase buffer", DEFAULT_REACTION["t4_ligase_buffer"]),
        ("T4 DNA ligase", DEFAULT_REACTION["t4_ligase"]),
        (f"{enzyme} restriction enzyme", DEFAULT_REACTION["restriction_enzyme"]),
    ]
    rows.extend((input_name, DEFAULT_REACTION["part"]) for input_name in dna_inputs)
    return rows


def build_markdown(assemblies):
    if not isinstance(assemblies, list) or not assemblies:
        raise ValueError("Input JSON must be a non-empty list of assembly dictionaries")

    lines = [
        "# Manual Golden Gate Assembly Protocol",
        "",
        "##Overview",
        " Golden Gate assembly is a one-pot DNA cloning method that uses a Type IIS restriction enzyme, such as BsaI, together with DNA ligase to assemble multiple DNA fragments in a predefined order. Because Type IIS enzymes cut outside their recognition sites, they generate custom overhangs that direct fragment assembly and allow the recognition sites to be removed from the final construct. In this protocol, plasmids containing DNA parts and a destination backbone are combined with the restriction enzyme and ligase in a single tube, then cycled in a thermocycler between digestion and ligation temperatures. Repetition of these cycles enriches for the correctly assembled composite plasmid, after which the enzymes are heat-inactivated and the reaction is held at 4 °C until collection.",
        "## Reaction Setup",
        "",
        f"- Total reaction volume: {DEFAULT_REACTION['total']} uL",
        f"- DNA input volume: {DEFAULT_REACTION['part']} uL per backbone or part",
        f"- Assemblies: {len(assemblies)}",
        "",
    ]

    for index, assembly in enumerate(assemblies, start=1):
        _validate_assembly(assembly, index)
        product_name = _name_from_uri(assembly["Product"])
        rows = _reaction_rows(assembly)

        lines.extend(
            [
                f"## Assembly {index}: {product_name}",
                "",
                "| Reagent | Volume (uL) |",
                "| --- | ---: |",
            ]
        )
        for reagent, volume in rows:
            lines.append(f"| {reagent} | {volume:g} |")

        lines.extend(
            [
                "",
                "1. Add reagents to a PCR tube or thermocycler plate well in the order listed.",
                "2. Mix gently by pipetting, then briefly spin down.",
                "3. Run the thermocycler program below.",
                "",
            ]
        )

    lines.extend(
        [
            "## Thermocycler Program",
            "",
            "| Step | Temperature | Time | Cycles |",
            "| --- | --- | --- | ---: |",
            "| Digest | 37 C | 2 min | 25 |",
            "| Ligate | 16 C | 5 min | 25 |",
            "| Final digestion | 50 C | 5 min | 1 |",
            "| Heat inactivation | 80 C | 10 min | 1 |",
            "| Hold | 4 C | indefinite | 1 |",
            "",
        ]
    )
    lines.extend(
        [
            "## Notes",
            "Thermocylcer iterations can be increased to improve the reaction efficiency.",
            "Assumes all DNA parts are available at suitable concentrations and added at equal molarity. Suggested molarities are 20 fmol/µL for parts and 10 fmol/µL for backbones.",
            "Store the assembly product at 4 °C for better stability until used for downstream applications.",
            "Validate assembled plasmids by restriction digest and gel electrophoresis, Sanger sequencing, or whole-plasmid sequencing."
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate a manual Golden Gate Markdown protocol.")
    parser.add_argument("--input", default="./assembly_product_assembly_plan.json", help="Path to SBOL-style JSON input file.")
    parser.add_argument("--output", default="./manual_assembly_protocol.md", help="Path to Markdown output file.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    assemblies = json.loads(input_path.read_text(encoding="utf-8"))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_markdown(assemblies), encoding="utf-8")

    print(f"Manual protocol written to {output_path}")


if __name__ == "__main__":
    main()
