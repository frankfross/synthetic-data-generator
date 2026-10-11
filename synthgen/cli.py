"""CLI: synthgen --schema schema.yaml --out data/ [--sqlite demo.db] [--seed 42]"""

from __future__ import annotations

import argparse
import json

from .generator import generate
from .outputs import write_csvs, write_sqlite
from .schema import load_schema


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate realistic relational fake data with FK consistency."
    )
    parser.add_argument("--schema", required=True, help="YAML schema file")
    parser.add_argument("--out", default="data",
                        help="output directory for CSV files")
    parser.add_argument("--sqlite", default=None,
                        help="also write a SQLite DB with FK constraints")
    parser.add_argument("--seed", type=int, default=None,
                        help="override the schema's seed")
    args = parser.parse_args(argv)

    schema = load_schema(args.schema)
    datasets = generate(schema, seed=args.seed)

    paths = write_csvs(datasets, args.out)
    if args.sqlite:
        write_sqlite(schema, datasets, args.sqlite)

    summary = {
        "tables": {name: len(rows) for name, rows in datasets.items()},
        "csv": paths,
        "sqlite": args.sqlite,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
