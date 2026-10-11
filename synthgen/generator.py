"""Row generation with referential integrity.

Tables are generated in dependency order (topological sort over the
foreign_key graph) so that a child table can sample FK values from its
parent's already-generated keys. Cycles are rejected — synthetic schemas
are DAGs.

Generation is deterministic: the schema's ``seed`` (or ``--seed``) drives
both a ``random.Random`` instance and Faker's seeding, so the same
schema + seed always yields the same dataset.
"""

from __future__ import annotations

import datetime as _dt
import random
import uuid

from faker import Faker


def dependency_order(tables):
    """Return table names parents-before-children; raise on cycles."""
    names = [t["name"] for t in tables]
    edges = {n: set() for n in names}  # child -> parents
    for table in tables:
        for col in table["columns"]:
            if col["type"] == "foreign_key":
                parent = col["to"].split(".", 1)[0]
                if parent != table["name"]:
                    edges[table["name"]].add(parent)
    ordered, permanent, temporary = [], set(), set()

    def visit(node):
        if node in permanent:
            return
        if node in temporary:
            raise ValueError(f"foreign key cycle detected involving '{node}'")
        temporary.add(node)
        for parent in sorted(edges[node]):
            visit(parent)
        temporary.discard(node)
        permanent.add(node)
        ordered.append(node)

    for name in names:
        visit(name)
    return ordered


def _parse_date(value):
    return _dt.date.fromisoformat(value)


class ValueFactory:
    """Produces one cell value per column spec.

    ``pools`` maps "table.column" -> list of generated values, so FK
    columns can sample from their parent table's keys.
    """

    def __init__(self, faker, rng, pools):
        self.fake = faker
        self.rng = rng
        self.pools = pools

    def make(self, col, row_state):
        ctype = col["type"]
        method = getattr(self, f"gen_{ctype}", None)
        if method is None:
            raise ValueError(f"no generator for type '{ctype}'")
        return method(col, row_state)

    def gen_pk(self, col, row_state):
        # sequential surrogate keys: deterministic and unique
        counter = row_state.get("__pk_counter__", 0) + 1
        row_state["__pk_counter__"] = counter
        return counter

    def gen_uuid(self, col, row_state):
        return str(uuid.UUID(int=self.rng.getrandbits(128)))

    def gen_int(self, col, row_state):
        return self.rng.randint(col["min"], col["max"])

    def gen_float(self, col, row_state):
        precision = col.get("precision", 2)
        return round(self.rng.uniform(col["min"], col["max"]), precision)

    def gen_choice(self, col, row_state):
        values = col["values"]
        weights = col.get("weights")
        if weights:
            return self.rng.choices(values, weights=weights, k=1)[0]
        return self.rng.choice(values)

    def gen_foreign_key(self, col, row_state):
        pool = self.pools.get(col["to"])
        if not pool:
            raise ValueError(
                f"column {col['name']}: no generated values for "
                f"FK target '{col['to']}' (check table order)"
            )
        return self.rng.choice(pool)

    def _gen_date(self, col, as_datetime):
        start = _parse_date(col["start"])
        end = _parse_date(col["end"])
        if start > end:
            raise ValueError(f"column {col['name']}: start date after end date")
        day = start + _dt.timedelta(
            days=self.rng.randint(0, (end - start).days))
        if not as_datetime:
            return day.isoformat()
        return _dt.datetime.combine(
            day,
            _dt.time(
                self.rng.randint(0, 23),
                self.rng.randint(0, 59),
                self.rng.randint(0, 59),
            ),
        ).isoformat(sep=" ")

    def gen_date(self, col, row_state):
        return self._gen_date(col, as_datetime=False)

    def gen_datetime(self, col, row_state):
        return self._gen_date(col, as_datetime=True)

    def gen_text(self, col, row_state):
        count = self.rng.randint(col.get("min_words", 5), col.get("max_words", 20))
        words = self.fake.words(nb=count)
        return " ".join(words).capitalize() + "."

    # faker-backed string fields
    def gen_name(self, col, row_state):
        return self.fake.name()

    def gen_first_name(self, col, row_state):
        return self.fake.first_name()

    def gen_last_name(self, col, row_state):
        return self.fake.last_name()

    def gen_email(self, col, row_state):
        return self.fake.email()

    def gen_phone(self, col, row_state):
        return self.fake.phone_number()

    def gen_address(self, col, row_state):
        return self.fake.street_address()

    def gen_city(self, col, row_state):
        return self.fake.city()

    def gen_state(self, col, row_state):
        return self.fake.state_abbr()

    def gen_zip(self, col, row_state):
        return self.fake.zipcode()

    def gen_country(self, col, row_state):
        return self.fake.country()

    def gen_company(self, col, row_state):
        return self.fake.company()

    def gen_job_title(self, col, row_state):
        return self.fake.job()


def generate(schema, seed=None):
    """Generate the full dataset.

    Returns a dict of table_name -> list of row dicts, in dependency
    (parent-first) order.
    """
    seed = schema.get("seed", 42) if seed is None else seed
    rng = random.Random(seed)
    fake = Faker()
    Faker.seed(seed)
    pools = {}  # "table.column" -> list of generated values (FK sampling)
    factory = ValueFactory(fake, rng, pools)

    tables = {t["name"]: t for t in schema["tables"]}
    order = dependency_order(schema["tables"])

    datasets = {}
    for name in order:
        table = tables[name]
        rows = []
        row_state = {}
        for _ in range(table["row_count"]):
            rows.append({c["name"]: factory.make(c, row_state)
                         for c in table["columns"]})
        _enforce_uniqueness(name, table, rows, factory, row_state)
        datasets[name] = rows
        for col in table["columns"]:
            pools[f"{name}.{col['name']}"] = [r[col["name"]] for r in rows]
    return datasets


def _enforce_uniqueness(table_name, table, rows, factory, row_state):
    for col in table["columns"]:
        if not col.get("unique"):
            continue
        seen, tries = set(), 0
        for row in rows:
            while row[col["name"]] in seen and tries < 10_000:
                row[col["name"]] = factory.make(col, row_state)
                tries += 1
            if row[col["name"]] in seen:
                raise ValueError(
                    f"table {table_name}: could not generate unique values "
                    f"for {col['name']}"
                )
            seen.add(row[col["name"]])
