# BuildCompiler Plating Protocol

## Plate
- Plate ID: `solid_96_well_plate`
- Protocol type: `manual`

## Input transformed strains
- 1_plated_A1_impl

## Parameters
- (none)

## 96-well plate map
| Well | Source transformed strain implementation | Plated strain implementation | Strain module |
|---|---|---|---|
| A1 | http://buildcompiler.org/E_coli_DH5alpha_with_standard_GFP_full_build_impl/1 | 1_plated_A1_impl | http://buildcompiler.org/E_coli_DH5alpha_with_standard_GFP_full_build/1 |

## Steps
1. Prepare one sterile solid-media 96-well plate.
2. Label the plate with the plate ID and date.
3. Transfer each transformed strain to the destination well shown in the map.
4. Incubate according to lab defaults or parameters above.
