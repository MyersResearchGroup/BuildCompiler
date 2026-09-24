"""Small reusable configuration validators, independent of execution backends."""

import math
from collections.abc import Mapping
from dataclasses import fields, replace


def positive(value: object, name: str) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number.")


def positive_integer(value: object, name: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer.")


class ConfigOverrides:
    """Replace only explicitly supplied fields, including False and defaults."""

    __slots__ = ()

    def with_overrides(self, overrides: Mapping[str, object]):
        unknown = set(overrides) - {field.name for field in fields(self)}
        if unknown:
            raise ValueError(f"Unknown configuration fields: {sorted(unknown)}")
        return replace(self, **overrides)
