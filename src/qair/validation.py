"""Validate generated documents against the schemas in ``schemas/``."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

__all__ = ["schemas_dir", "load_schema", "validate_document"]


def schemas_dir(start: Path | str | None = None) -> Path:
    here = Path(start) if start is not None else Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        target = candidate / "schemas"
        if target.is_dir() and any(target.glob("*.schema.json")):
            return target
    raise FileNotFoundError("No schemas/ directory found above " + str(here))


@lru_cache(maxsize=None)
def _validator(name: str, directory: str) -> jsonschema.Draft202012Validator:
    schema = json.loads((Path(directory) / f"{name}.schema.json").read_text())
    # FormatChecker turns "format": "date-time" into a real check rather than an
    # annotation, which is the point of declaring it.
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


def load_schema(name: str, directory: Path | str | None = None) -> dict[str, Any]:
    d = Path(directory) if directory is not None else schemas_dir()
    return json.loads((d / f"{name}.schema.json").read_text())


def validate_document(document: Any, schema_name: str, directory: Path | str | None = None) -> None:
    """Raise jsonschema.ValidationError if the document does not conform."""
    d = str(Path(directory) if directory is not None else schemas_dir())
    _validator(schema_name, d).validate(document)
