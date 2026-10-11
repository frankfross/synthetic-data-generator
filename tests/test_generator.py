"""Tests for synthetic-data-generator."""

import csv
import sqlite3

import pytest

from synthgen.generator import dependency_order, generate
from synthgen.schema import load_schema, validate
from synthgen.outputs import write_csvs, write_sqlite

RETAIL = "schemas/retail.yaml"


def retail_schema():
    return load_schema(RETAIL)


def fk_consistent(datasets, child, fk_col, parent):
    parent_ids = {r["id"] for r in datasets[parent]}
    return all(r[fk_col] in parent_ids for r in datasets[child])


def test_schema_validation_rejects_unknown_type():
    with pytest.raises(ValueError, match="unsupported type"):
        validate({"tables": [{
            "name": "t", "row_count": 1,
            "columns": [{"name": "x", "type": "teleport"}]}]})


def test_schema_validation_rejects_bad_fk_target():
    with pytest.raises(ValueError, match="unknown target"):
        validate({"tables": [{
            "name": "t", "row_count": 1,
            "columns": [{"name": "x", "type": "foreign_key",
                         "to": "nope.id"}]}]})


def test_schema_validation_requires_type_params():
    with pytest.raises(ValueError, match="requires 'values'"):
        validate({"tables": [{
            "name": "t", "row_count": 1,
            "columns": [{"name": "x", "type": "choice"}]}]})


def test_dependency_order_parents_first():
    order = dependency_order(retail_schema()["tables"])
    assert order.index("customers") < order.index("orders")
    assert order.index("products") < order.index("order_items")
    assert order.index("orders") < order.index("order_items")


def test_dependency_order_rejects_cycles():
    schema = {"tables": [
        {"name": "a", "row_count": 1, "columns": [
            {"name": "id", "type": "pk"},
            {"name": "b_id", "type": "foreign_key", "to": "b.id"}]},
        {"name": "b", "row_count": 1, "columns": [
            {"name": "id", "type": "pk"},
            {"name": "a_id", "type": "foreign_key", "to": "a.id"}]},
    ]}
    with pytest.raises(ValueError, match="cycle"):
        dependency_order(schema["tables"])


def test_row_counts_match_schema():
    datasets = generate(retail_schema())
    assert {n: len(r) for n, r in datasets.items()} == {
        "customers": 1000, "products": 200,
        "orders": 5000, "order_items": 12000,
    }


def test_pk_sequential_and_unique():
    datasets = generate(retail_schema())
    for name, rows in datasets.items():
        ids = [r["id"] for r in rows]
        assert ids == list(range(1, len(rows) + 1))
        assert len(set(ids)) == len(ids)


def test_foreign_keys_consistent():
    datasets = generate(retail_schema())
    assert fk_consistent(datasets, "orders", "customer_id", "customers")
    assert fk_consistent(datasets, "order_items", "order_id", "orders")
    assert fk_consistent(datasets, "order_items", "product_id", "products")


def test_unique_columns_unique():
    datasets = generate(retail_schema())
    emails = [r["email"] for r in datasets["customers"]]
    assert len(set(emails)) == len(emails)


def test_int_float_ranges():
    datasets = generate(retail_schema())
    items = datasets["order_items"]
    assert all(1 <= r["quantity"] <= 10 for r in items)
    assert all(0.0 <= r["discount_pct"] <= 0.4 for r in items)
    assert all(4.99 <= r["unit_price"] <= 1499.99
               for r in datasets["products"])


def test_choice_values_and_weights():
    datasets = generate(retail_schema())
    segments = {r["segment"] for r in datasets["customers"]}
    assert segments <= {"standard", "premium", "enterprise"}
    statuses = {r["status"] for r in datasets["orders"]}
    assert statuses <= {"completed", "shipped", "cancelled", "refunded"}


def test_deterministic_with_seed():
    a = generate(retail_schema(), seed=7)
    b = generate(retail_schema(), seed=7)
    assert a == b
    c = generate(retail_schema(), seed=8)
    assert a["orders"] != c["orders"]


def test_write_csvs_roundtrip(tmp_path):
    schema = load_schema(RETAIL)
    schema["tables"] = [dict(t, row_count=10) for t in schema["tables"]]
    datasets = generate(schema, seed=1)
    paths = write_csvs(datasets, str(tmp_path / "data"))
    with open(paths["customers"], encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 10
    assert rows[0]["full_name"] == datasets["customers"][0]["full_name"]


def test_write_sqlite_enforces_fks(tmp_path):
    schema = load_schema(RETAIL)
    schema["tables"] = [dict(t, row_count=5) for t in schema["tables"]]
    datasets = generate(schema, seed=1)
    db = str(tmp_path / "demo.db")
    write_sqlite(schema, datasets, db)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    counts = {name: conn.execute(
        f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        for name in datasets}
    assert counts == {"customers": 5, "products": 5, "orders": 5,
                      "order_items": 5}
    # orphan FK insert must be rejected
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            'INSERT INTO "orders" (id, customer_id, order_ts, status, channel)'
            ' VALUES (999, 99999, "2024-01-01", "completed", "web")')
    conn.close()
