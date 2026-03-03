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

PART_ROLES = {
    "http://identifiers.org/so/SO:0000167",  # promoter
    "http://identifiers.org/so/SO:0000139",  # RBS
    "http://identifiers.org/so/SO:0000316",  # CDS
    "http://identifiers.org/so/SO:0000141",  # terminator
}

KAN = "Kanamycin"
AMP = "Ampicillin"

ANTIBIOTIC_MAP = {
    "kan": KAN,
    "amp": AMP,
}

ENGINEERED_PLASMID = "http://identifiers.org/so/SO:0000637"
ENGINEERED_INSERT = "https://identifiers.org/so/SO:0000915"
ENGINEERED_REGION = "http://identifiers.org/so/SO:0000804"
PLASMID_VECTOR = "https://identifiers.org/so/SO:0000755"
PLASMID_CLONING_VECTOR = "https://identifiers.org/ncit/NCIT:C1919"
ANTIBIOTIC_RESISTANCE = "https://identifiers.org/ncit/NCIT:C17449"
RESTRICTION_ENZYME_ASSEMBLY_SCAR = "http://identifiers.org/so/SO:0001953"
ORGANISM_STRAIN = "https://identifiers.org/ncit/NCIT:C14419"

FIVE_PRIME_OVERHANG = "http://identifiers.org/so/SO:0001932"
THREE_PRIME_OVERHANG = "http://identifiers.org/so/SO:0001933"

SINGLE_STRANDED = "http://identifiers.org/so/SO:0000984"
CIRCULAR = "http://identifiers.org/so/SO:0000988"
LINEAR = "http://identifiers.org/so/SO:0000987"

DNA_TYPES = {  # TODO see about restricting dna types to only accept dna
    "http://www.biopax.org/release/biopax-level3.owl#Dna",
    "http://www.biopax.org/release/biopax-level3.owl#DnaRegion",
}
