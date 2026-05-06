"""Pure full-build planner orchestration."""

from __future__ import annotations

from collections.abc import Iterable

import sbol2

from buildcompiler.api.options import BuildOptions
from buildcompiler.planning.classifier import classify_non_combinatorial
from buildcompiler.planning.combinatorial import expand_combinatorial_derivation
from buildcompiler.planning.models import BuildPlan, UnsupportedPlanningRecord
from buildcompiler.sbol import SbolResolver


class FullBuildPlanner:
    def __init__(
        self,
        *,
        options: BuildOptions | None = None,
        resolver: SbolResolver | None = None,
    ):
        self.options = options or BuildOptions()
        self.resolver = resolver

    def plan(
        self, abstract_designs: Iterable[object], *, options: BuildOptions | None = None
    ) -> BuildPlan:
        active = options or self.options
        out = BuildPlan()
        for design in abstract_designs:
            if isinstance(design, sbol2.CombinatorialDerivation):
                reqs, unsupported, warnings = expand_combinatorial_derivation(
                    design, options=active
                )
                out.lvl1_requests.extend(reqs)
                out.unsupported.extend(unsupported)
                out.warnings.extend(warnings)
                continue
            classified = classify_non_combinatorial(design)
            if isinstance(classified, UnsupportedPlanningRecord):
                out.unsupported.append(classified)
            elif classified.stage.value == "assembly_lvl2":
                out.lvl2_requests.append(classified)
            elif classified.stage.value == "assembly_lvl1":
                out.lvl1_requests.append(classified)
            else:
                out.domestication_requests.append(classified)
        return out
