"""Dataset writers: one CSV per table, or a SQLite DB with FK constraints."""

from __future__ import annotations

import csv
import os
import sqlite3

# synthgen column type -> SQLite storage class
SQLITE_TYPES = {
    "pk": "INTEGER",
    "uuid": "TEXT",
    "int": "INTEGER",
    "float": "REAL",
    "choice": "TEXT",
    "foreign_key": "INTEGER",
    "date": "TEXT",
    "datetime": "TEXT",
    "text": "TEXT",
    "name": "TEXT",
    "first_name": "TEXT",
    "last_name": "TEXT",
    "email": "TEXT",
    "phone": "TEXT",
    "address": "TEXT",
    "city": "TEXT",
    "state": "TEXT",
    "zip": "TEXT",
    "country": "TEXT",
    "company": "TEXT",
    "job_title": "TEXT",
}


def write_csvs(datasets, out_dir):
    """Write one <table>.csv per table into out_dir."""
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    for name, rows in datasets.items():
        path = os.path.join(out_dir, f"{name}.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        paths[name] = path
    return paths


def write_sqlite(schema, datasets, db_path):
    """Create a SQLite DB with one table per dataset + FK constraints."""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    tables = {t["name"]: t for t in schema["tables"]}
    for name, rows in datasets.items():
        table = tables[name]
        cols, constraints = [], []
        for col in table["columns"]:
            col_def = f'"{col["name"]}" {SQLITE_TYPES[col["type"]]}'
            if col["type"] == "pk":
                col_def += " PRIMARY KEY"
            cols.append(col_def)
            if col["type"] == "foreign_key":
                parent_table, parent_col = col["to"].split(".", 1)
                constraints.append(
                    f'FOREIGN KEY ("{col["name"]}") '
                    f'REFERENCES "{parent_table}" ("{parent_col}")'
                )
        ddl = f'CREATE TABLE IF NOT EXISTS "{name}" (\n  ' + ",\n  ".join(
            cols + constraints) + "\n)"
        conn.execute(f'DROP TABLE IF EXISTS "{name}"')
        conn.execute(ddl)
        placeholders = ", ".join("?" for _ in table["columns"])
        col_names = ", ".join(f'"{c["name"]}"' for c in table["columns"])
        conn.executemany(
            f'INSERT INTO "{name}" ({col_names}) VALUES ({placeholders})',
            [[r[c["name"]] for c in table["columns"]] for r in rows],
        )
    conn.commit()
    conn.close()
    return db_path
