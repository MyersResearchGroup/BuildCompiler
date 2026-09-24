"""In-memory artifacts and an explicit, opt-in filesystem boundary."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True, kw_only=True)
class ProtocolArtifact:
    name: str
    media_type: str
    content: str

    def __post_init__(self) -> None:
        if (
            not self.name
            or self.name in (".", "..")
            or Path(self.name).name != self.name
            or "\\" in self.name
        ):
            raise ValueError("Artifact names must be plain filenames.")


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactBundle:
    artifacts: tuple[ProtocolArtifact, ...]

    def __post_init__(self) -> None:
        if len({artifact.name for artifact in self.artifacts}) != len(self.artifacts):
            raise ValueError("Artifact filenames must be unique.")

    def write(
        self, directory: str | Path, *, overwrite: bool = False
    ) -> tuple[Path, ...]:
        """Write only when called, refusing existing files by default."""
        output = Path(directory)
        paths = tuple(output / artifact.name for artifact in self.artifacts)
        if not overwrite and any(path.exists() for path in paths):
            raise FileExistsError("One or more output artifacts already exist.")
        output.mkdir(parents=True, exist_ok=True)
        for path, artifact in zip(paths, self.artifacts, strict=True):
            with path.open("w" if overwrite else "x", encoding="utf-8") as handle:
                handle.write(artifact.content)
        return paths
