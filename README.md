# synthetic-data-generator

Realistic relational fake data with referential integrity — declare your
schema in YAML, get out CSVs and/or a SQLite database whose foreign keys
actually line up. Built for seeding dev/staging environments and for
generating test fixtures for data pipelines (every child FK value is
sampled from its parent table's generated keys, so joins never dangle).

Portfolio project (knowledge demo — generates local fake data with Faker,
no prod claims).

## Layout

```
synthgen/
  schema.py      # YAML schema loading + validation (types, FK targets, cycles)
  generator.py   # dependency-ordered generation, ValueFactory per column type
  outputs.py     # one CSV per table; SQLite writer with real FK constraints
  cli.py         # --schema --out --sqlite --seed
schemas/
  retail.yaml    # sample: customers -> orders -> order_items (+ products)
tests/           # pytest: validation, topo order, FK consistency, determinism,
                 #   CSV roundtrip, SQLite FK enforcement
```

## Quickstart

```bash
pip install -r requirements.txt

python3 -m synthgen.cli --schema schemas/retail.yaml --out data --sqlite demo.db
```

```json
{
  "tables": {
    "customers": 1000,
    "products": 200,
    "orders": 5000,
    "order_items": 12000
  },
  "csv": {
    "customers": "data/customers.csv",
    "products": "data/products.csv",
    "orders": "data/orders.csv",
    "order_items": "data/order_items.csv"
  },
  "sqlite": "demo.db"
}
```

`data/customers.csv`:

```
id,full_name,email,city,state,signup_date,segment
1,Allison Hill,donaldgarcia@example.net,New Roberttown,CO,2025-08-02,standard
2,Jonathan Johnson,jennifermiles@example.com,South Bridget,AS,2023-07-18,standard
3,Olivia Moore,jpeterson@example.org,Curtisfurt,CT,2022-10-13,premium
```

Generation is seeded (schema's `seed:` or `--seed`), so the same schema
always produces the same dataset — fixtures stay reproducible.

## Schema format

```yaml
seed: 42
tables:
  - name: orders
    row_count: 5000
    columns:
      - name: id
        type: pk                        # sequential surrogate key, unique
      - name: customer_id
        type: foreign_key
        to: customers.id                # sampled from generated parent keys
      - name: order_ts
        type: datetime
        start: "2023-01-01"
        end: "2025-12-31"
      - name: status
        type: choice
        values: ["completed", "shipped", "cancelled", "refunded"]
        weights: [80, 12, 5, 3]         # optional; uniform without weights
      - name: total
        type: float
        min: 5.0
        max: 2000.0
      - name: email
        type: email
        unique: true                     # uniqueness enforced per column
```

Supported types: `pk`, `uuid`, `int` (min/max), `float` (min/max/precision),
`choice` (values + optional weights), `foreign_key` (to: table.column),
`date` / `datetime` (start/end), `text` (min/max words), plus Faker-backed
`name`, `first_name`, `last_name`, `email`, `phone`, `address`, `city`,
`state`, `zip`, `country`, `company`, `job_title`.

## Design notes

- **Parents before children.** Tables are topologically sorted over the FK
  graph; FK columns sample from the parent table's already-generated key
  pool (uniform random). Self-references within a table are generated in
  row order and excluded from the topo edges; cross-table cycles are
  rejected as invalid schemas.
- **Deterministic.** One `random.Random` instance plus a seeded Faker drive
  everything, so `--seed` reproduces the exact dataset — important when
  fixtures back automated tests.
- **Validated early.** The schema loader rejects unknown types, missing
  required params, unknown FK targets, duplicate names, and bad ranges
  before a single row is generated.
- **Honest bounds.** `unique: true` columns are re-rolled (bounded retries)
  rather than silently duplicated; if the value space is exhausted the run
  fails loudly instead of producing bad data.
- **SQLite output is constraint-checked.** Tables are created with real
  `PRIMARY KEY` / `FOREIGN KEY` constraints under `PRAGMA foreign_keys =
  ON`, so an FK bug fails at insert time instead of hiding in the data.
