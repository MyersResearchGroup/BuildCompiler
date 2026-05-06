from __future__ import annotations
import itertools
import sbol2
from buildcompiler.api import BuildOptions
from buildcompiler.domain import BuildRequest, BuildStage, BuildWarning, DesignKind
from buildcompiler.planning.classifier import request_id_for
from buildcompiler.planning.models import UnsupportedPlanningRecord
from buildcompiler.planning.validation import ROLE_TO_NAME


def _collect_variant_sets(derivation):
    variables = list(derivation.variableComponents)
    variables.sort(
        key=lambda variable: (str(getattr(variable, "variable", "")), variable.identity)
    )
    return variables, [sorted(list(vc.variants), key=str) for vc in variables]


def expand_combinatorial_derivation(
    derivation: sbol2.CombinatorialDerivation, *, options: BuildOptions
):
    warnings = []
    unsupported = []
    requests = []
    variables, variant_sets = _collect_variant_sets(derivation)
    if not variant_sets or any(len(v) == 0 for v in variant_sets):
        unsupported.append(
            UnsupportedPlanningRecord(
                derivation.identity,
                derivation.displayId,
                DesignKind.COMBINATORIAL_DERIVATION,
                "Variable component has no listed variants.",
            )
        )
        return requests, unsupported, warnings
    total = 1
    for v in variant_sets:
        total *= len(v)
    if (
        total > options.planning.combinatorial.max_variants
        and not options.planning.combinatorial.allow_large_expansion
    ):
        warnings.append(
            BuildWarning(
                "planning.combinatorial.expansion_blocked",
                "Combinatorial expansion exceeds max_variants and is blocked.",
                BuildStage.ASSEMBLY_LVL1,
                derivation.identity,
                {
                    "variant_count": total,
                    "max_variants": options.planning.combinatorial.max_variants,
                },
            )
        )
        unsupported.append(
            UnsupportedPlanningRecord(
                derivation.identity,
                derivation.displayId,
                DesignKind.COMBINATORIAL_DERIVATION,
                "Combinatorial expansion blocked by max_variants.",
                {"variant_count": total},
            )
        )
        return requests, unsupported, warnings
    doc = derivation.doc
    valid = 0
    for idx, chosen in enumerate(itertools.product(*variant_sets)):
        roles = []
        for pid in chosen:
            obj = doc.find(pid) if doc is not None else None
            if isinstance(obj, sbol2.ComponentDefinition):
                matching = [ROLE_TO_NAME[r] for r in obj.roles if r in ROLE_TO_NAME]
                if len(matching) == 1:
                    roles.append(matching[0])
        if sorted(roles) != ["cds", "promoter", "rbs", "terminator"]:
            warnings.append(
                BuildWarning(
                    "planning.combinatorial.invalid_variant",
                    "Skipping invalid combinatorial variant.",
                    BuildStage.ASSEMBLY_LVL1,
                    derivation.identity,
                    {"variant_index": idx},
                )
            )
            continue
        requests.append(
            BuildRequest(
                request_id_for(
                    BuildStage.ASSEMBLY_LVL1,
                    derivation.identity,
                    derivation.displayId,
                    variant_index=idx,
                ),
                BuildStage.ASSEMBLY_LVL1,
                derivation.identity,
                derivation.displayId,
                DesignKind.COMBINATORIAL_DERIVATION,
                parent_group=derivation.identity,
                variant_index=idx,
                constraints={"part_order": list(chosen)},
            )
        )
        valid += 1
    if valid == 0:
        unsupported.append(
            UnsupportedPlanningRecord(
                derivation.identity,
                derivation.displayId,
                DesignKind.COMBINATORIAL_DERIVATION,
                "All combinatorial variants were invalid.",
            )
        )
    return requests, unsupported, warnings
