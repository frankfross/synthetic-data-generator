"""synthetic-data-generator: realistic relational fake data with FK consistency."""

from .schema import load_schema, validate
from .generator import generate

__all__ = ["load_schema", "validate", "generate"]
