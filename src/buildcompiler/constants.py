FUSION_SITES = {
    "A": "GGAG",
    "B": "TACT",
    "C": "AATG",
    "D": "AGGT",
    "E": "GCTT",
    "F": "CGCT",
    "G": "TGCC",
    "H": "ACTA",
}

KAN = "Kanamycin"
AMP = "Ampicillin"

ANTIBIOTIC_MAP = {
    "kan": KAN,
    "amp": AMP,
}

ENGINEERED_PLASMID = "http://identifiers.org/so/SO:0000637"
PLASMID_CLONING_VECTOR = "https://identifiers.org/ncit/NCIT:C1919"
ANTIBIOTIC_RESISTANCE = "https://identifiers.org/ncit/NCIT:C17449"
RESTRICTION_ENZYME_ASSEMBLY_SCAR = "http://identifiers.org/so/SO:0001953"

DNA_TYPES = {  # TODO see about restricting dna types to only accept dna
    "http://www.biopax.org/release/biopax-level3.owl#Dna",
    "http://www.biopax.org/release/biopax-level3.owl#DnaRegion",
}
