"""Schema loading and validation.

A schema is a YAML document like:

    seed: 42
    tables:
      - name: customers
        row_count: 1000
        columns:
          - name: id
            type: pk
          - name: email
            type: email
            unique: true
      - name: orders
        row_count: 5000
        columns:
          - name: id
            type: pk
          - name: customer_id
            type: foreign_key
            to: customers.id
"""

from __future__ import annotations

import yaml

REQUIRED_TYPE_PARAMS = {
    "int": {"min", "max"},
    "float": {"min", "max"},
    "choice": {"values"},
    "date": {"start", "end"},
    "datetime": {"start", "end"},
    "foreign_key": {"to"},
    "text": set(),
    "pk": set(),
}

# Every type the generator knows how to produce. Anything else is rejected.
SUPPORTED_TYPES = set(REQUIRED_TYPE_PARAMS) | {
    "name", "first_name", "last_name", "email", "phone",
    "address", "city", "state", "zip", "country", "company",
    "job_title", "uuid",
}


def load_schema(path):
    """Load and validate a schema file; return the parsed dict."""
    with open(path, "r", encoding="utf-8") as fh:
        schema = yaml.safe_load(fh)
    validate(schema)
    return schema


def validate(schema):
    if not isinstance(schema, dict):
        raise ValueError("schema must be a mapping with a 'tables' key")
    tables = schema.get("tables")
    if not tables:
        raise ValueError("schema must define at least one table")

    seen = set()
    for table in tables:
        name = table.get("name")
        if not name:
            raise ValueError("every table needs a 'name'")
        if name in seen:
            raise ValueError(f"duplicate table name: {name}")
        seen.add(name)
        if not isinstance(table.get("row_count"), int) or table["row_count"] <= 0:
            raise ValueError(f"table {name}: row_count must be a positive int")
        columns = table.get("columns")
        if not columns:
            raise ValueError(f"table {name}: needs at least one column")
        col_names = set()
        pk_count = 0
        for col in columns:
            cname = col.get("name")
            if not cname:
                raise ValueError(f"table {name}: every column needs a 'name'")
            if cname in col_names:
                raise ValueError(f"table {name}: duplicate column name {cname}")
            col_names.add(cname)
            ctype = col.get("type")
            if ctype not in SUPPORTED_TYPES:
                raise ValueError(
                    f"table {name}.{cname}: unsupported type '{ctype}' "
                    f"(supported: {sorted(SUPPORTED_TYPES)})"
                )
            if ctype == "pk":
                pk_count += 1
            for param in REQUIRED_TYPE_PARAMS.get(ctype, ()):
                if param not in col:
                    raise ValueError(
                        f"table {name}.{cname}: type '{ctype}' requires '{param}'"
                    )
            if ctype in ("int", "float") and col["min"] >= col["max"]:
                raise ValueError(
                    f"table {name}.{cname}: min must be < max"
                )
        if pk_count > 1:
            raise ValueError(f"table {name}: at most one 'pk' column")

    # foreign_key targets must point at real tables/columns
    col_index = {
        (t["name"], c["name"]) for t in tables for c in t["columns"]
    }
    for table in tables:
        for col in table["columns"]:
            if col["type"] == "foreign_key":
                try:
                    target_table, target_col = col["to"].split(".", 1)
                except ValueError:
                    raise ValueError(
                        f"table {table['name']}.{col['name']}: 'to' must look "
                        f"like 'table.column', got '{col['to']}'"
                    )
                if (target_table, target_col) not in col_index:
                    raise ValueError(
                        f"table {table['name']}.{col['name']}: unknown target "
                        f"'{col['to']}'"
                    )
