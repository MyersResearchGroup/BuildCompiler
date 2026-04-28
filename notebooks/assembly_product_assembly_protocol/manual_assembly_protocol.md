# Manual Golden Gate Assembly Protocol

## Overview
 Golden Gate assembly is a one-pot DNA cloning method that uses a Type IIS restriction enzyme, such as BsaI, together with DNA ligase to assemble multiple DNA fragments in a predefined order. Because Type IIS enzymes cut outside their recognition sites, they generate custom overhangs that direct fragment assembly and allow the recognition sites to be removed from the final construct. In this protocol, plasmids containing DNA parts and a destination backbone are combined with the restriction enzyme and ligase in a single tube, then cycled in a thermocycler between digestion and ligation temperatures. Repetition of these cycles enriches for the correctly assembled composite plasmid, after which the enzymes are heat-inactivated and the reaction is held at 4 °C until collection.
## Reaction Setup

- Total reaction volume: 20 uL
- DNA input volume: 2 uL per backbone or part
- Assemblies: 1

## Assembly 1: assembly_product_1

| Reagent | Volume (uL) |
| --- | ---: |
| Nuclease-free water | 2 |
| T4 DNA ligase buffer | 2 |
| T4 DNA ligase | 4 |
| [BsaI restriction enzyme](https://synbiohub.org/user/Gon/Enzyme_Implementations/BsaI/1) | 2 |
| [dvk_backbone_core](https://synbiohub.org/user/Gon/CIDARMoCloParts/dvk_backbone_core/1) | 2 |
| [J23100](https://synbiohub.org/user/Gon/CIDARMoCloParts/J23100/1) | 2 |
| [B0034](https://synbiohub.org/user/Gon/CIDARMoCloParts/B0034/1) | 2 |
| [E0040m_gfp](https://synbiohub.org/user/Gon/CIDARMoCloParts/E0040m_gfp/1) | 2 |
| [B0015](https://synbiohub.org/user/Gon/CIDARMoCloParts/B0015/1) | 2 |

1. Add reagents to a PCR tube or thermocycler plate well in the order listed.
2. Mix gently by pipetting, then briefly spin down.
3. Run the thermocycler program below.

## Thermocycler Program

| Step | Temperature | Time | Cycles |
| --- | --- | --- | ---: |
| Digest | 37 C | 2 min | 25 |
| Ligate | 16 C | 5 min | 25 |
| Final digestion | 50 C | 5 min | 1 |
| Heat inactivation | 80 C | 10 min | 1 |
| Hold | 4 C | indefinite | 1 |

## Notes
Thermocylcer iterations can be increased to improve the reaction efficiency.
Assumes all DNA parts are available at suitable concentrations and added at equal molarity. Suggested molarities are 20 fmol/µL for parts and 10 fmol/µL for backbones.
Store the assembly product at 4 °C for better stability until used for downstream applications.
Validate assembled plasmids by restriction digest and gel electrophoresis, Sanger sequencing, or whole-plasmid sequencing.