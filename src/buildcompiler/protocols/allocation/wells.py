"""Well geometry with explicit, deterministic column-major traversal."""

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class WellGrid:
    rows: int
    columns: int

    def __post_init__(self) -> None:
        if type(self.rows) is not int or not 1 <= self.rows <= 26:
            raise ValueError("rows must be an integer between 1 and 26.")
        if type(self.columns) is not int or self.columns < 1:
            raise ValueError("columns must be a positive integer.")

    @property
    def capacity(self) -> int:
        return self.rows * self.columns

    def name(self, index: int) -> str:
        if type(index) is not int or not 0 <= index < self.capacity:
            raise ValueError(f"Well index {index} is outside this grid.")
        return f"{chr(ord('A') + index % self.rows)}{index // self.rows + 1}"

    def index(self, name: str) -> int:
        match = re.fullmatch(r"([A-Z])([1-9][0-9]*)", name)
        if not match:
            raise ValueError(f"Invalid well name: {name!r}")
        row = ord(match[1]) - ord("A")
        column = int(match[2]) - 1
        if row >= self.rows or column >= self.columns:
            raise ValueError(f"Well {name} is outside this grid.")
        return column * self.rows + row


PLATE_96 = WellGrid(rows=8, columns=12)
BLOCK_24 = WellGrid(rows=4, columns=6)
