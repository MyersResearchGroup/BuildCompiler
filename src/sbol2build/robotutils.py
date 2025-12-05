import sbol2
import json

def assembly_plan_RDF_to_JSON(file):
    if type(file)==sbol2.Document:
        doc = file
    else:
        sbol2.Config.setOption('sbol_typed_uris', False)
        doc = sbol2.Document()
        doc.read(file)

    # Known SO roles
    PRODUCT_ROLE = 'http://identifiers.org/so/SO:0000804'
    BackBone_ROLE = 'http://identifiers.org/so/SO:0000755'
    ENZYME_ROLE = 'http://identifiers.org/obi/OBI:0000732'

    PARTS_ROLE_LIST = [
        'http://identifiers.org/so/SO:0000031', 'http://identifiers.org/so/SO:0000316',
        'http://identifiers.org/so/SO:0001977', 'http://identifiers.org/so/SO:0001956',
        'http://identifiers.org/so/SO:0000188', 'http://identifiers.org/so/SO:0000839',
        'http://identifiers.org/so/SO:0000167', 'http://identifiers.org/so/SO:0000139',
        'http://identifiers.org/so/SO:0001979', 'http://identifiers.org/so/SO:0001955',
        'http://identifiers.org/so/SO:0001546', 'http://identifiers.org/so/SO:0001263',
        'http://identifiers.org/SO:0000141', 'http://identifiers.org/so/SO:0000141'
    ]

    product_dicts = []
    globalEnzyme = None

    for cd in doc.componentDefinitions:
        print(f"\n🔍 Checking Component: {cd.displayId}")
        print(f"  Types: {cd.types}")
        print(f"  Roles: {cd.roles}")

        if ENZYME_ROLE in cd.roles:
            globalEnzyme = cd.identity
            print(f"✅ Found enzyme definition: {globalEnzyme}")

        if PRODUCT_ROLE in cd.roles:
            result = {
                'Product': cd.identity,
                'Backbone': None,
                'PartsList': [],
                'Restriction Enzyme': None
            }

            for comp in cd.components:
                sub_cd = doc.componentDefinitions.get(comp.definition)
                if sub_cd is None:
                    print(f"⚠️ Component definition for {comp.displayId} not found.")
                    continue

                print(f"  → Subcomponent: {sub_cd.displayId}")
                print(f"    Roles: {sub_cd.roles}")

                if BackBone_ROLE in sub_cd.roles:
                    result['Backbone'] = sub_cd.identity
                    print(f"    🧬 Assigned Backbone: {sub_cd.identity}")

                if any(role in PARTS_ROLE_LIST for role in sub_cd.roles):
                    result['PartsList'].append(sub_cd.identity)
                    print(f"    🧩 Added Part: {sub_cd.identity}")

            if not result['Backbone']:
                print(f"⚠️ No backbone found for product {cd.displayId}")
            if not result['PartsList']:
                print(f"⚠️ No parts found for product {cd.displayId}")

            product_dicts.append(result)

    for entry in product_dicts:
        entry['Restriction Enzyme'] = globalEnzyme

    with open('output.json', 'w') as json_file:
        json.dump(product_dicts, json_file, indent=4)

    return product_dicts
