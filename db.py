"""SQLite catalog the agent queries with its own SQL.

Build:  python db.py

The agent does not get raw table access. `run_sql` opens a read-only connection
and exposes a single TEMP VIEW called `catalog`, pre-scoped to the category the
shopper picked and to in-stock rows only. Whatever SQL the agent writes, it
cannot reach another category, an out-of-stock item, or a write.

How the agent should *use* this is documented in skills/search-products/SKILL.md,
not encoded here.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from models import Catalog, Product

ROOT = Path(__file__).resolve().parent
PRODUCTS_JSON = ROOT / "data" / "products.json"
DB_PATH = ROOT / "data" / "catalog.db"

CATEGORIES: dict[str, str] = {
    "coffee_table": "Coffee Tables",
    "dining_table": "Dining Tables",
    "side_table": "Side & Accent Tables",
    "console_table": "Consoles",
    "tv_unit": "TV Units",
    "shoe_storage": "Shoe Holders & Cabinets",
}

MAX_ROWS = 50

SCHEMA = """
DROP TABLE IF EXISTS products;

CREATE TABLE products (
    id                TEXT PRIMARY KEY,
    sku               TEXT NOT NULL UNIQUE,
    name              TEXT NOT NULL,
    brand             TEXT NOT NULL,
    category          TEXT NOT NULL,
    short_description TEXT NOT NULL,
    description       TEXT NOT NULL,

    price             REAL NOT NULL,          -- effective price paid today
    list_price        REAL NOT NULL,
    on_sale           INTEGER NOT NULL,

    width_cm          REAL NOT NULL,
    depth_cm          REAL NOT NULL,
    height_cm         REAL NOT NULL,
    weight_kg         REAL NOT NULL,

    primary_material  TEXT NOT NULL,
    materials         TEXT NOT NULL,          -- comma-separated
    finish            TEXT NOT NULL,
    colors            TEXT NOT NULL,          -- comma-separated colour names
    color_families    TEXT NOT NULL,          -- comma-separated
    styles            TEXT NOT NULL,          -- comma-separated
    room_types        TEXT NOT NULL,          -- comma-separated
    tags              TEXT NOT NULL,          -- comma-separated

    storage_type      TEXT NOT NULL,
    drawers           INTEGER NOT NULL,
    shelves           INTEGER NOT NULL,
    wall_mounted      INTEGER NOT NULL,
    extendable        INTEGER NOT NULL,
    cable_management  INTEGER NOT NULL,
    assembly_minutes  INTEGER NOT NULL,

    attributes        TEXT NOT NULL,          -- JSON, category-specific extras
    care              TEXT NOT NULL,
    rating            REAL NOT NULL,
    reviews_count     INTEGER NOT NULL,
    in_stock          INTEGER NOT NULL,
    lead_time_days    INTEGER NOT NULL,
    image_main        TEXT,
    product_url       TEXT NOT NULL
);

CREATE INDEX idx_category ON products(category);
CREATE INDEX idx_price    ON products(price);
CREATE INDEX idx_stock    ON products(in_stock);

"""


def load_catalog() -> Catalog:
    return Catalog.model_validate_json(PRODUCTS_JSON.read_text(encoding="utf-8"))


def build(db_path: Path = DB_PATH) -> int:
    catalog = load_catalog()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        for p in catalog.products:
            colors = ", ".join(c.name for c in p.colors)
            families = ", ".join(sorted({c.family for c in p.colors}))
            materials = ", ".join(p.materials)
            styles = ", ".join(p.styles)
            rooms = ", ".join(p.room_types)
            tags = ", ".join(p.tags)
            conn.execute(
                "INSERT INTO products VALUES (" + ",".join("?" * 37) + ")",
                (
                    p.id, p.sku, p.name, p.brand, p.category,
                    p.short_description, p.description,
                    p.price.effective, p.price.amount, int(p.price.on_sale),
                    p.dimensions_cm.width, p.dimensions_cm.depth, p.dimensions_cm.height,
                    p.weight_kg,
                    p.primary_material, materials, p.finish, colors, families,
                    styles, rooms, tags,
                    p.storage_type, p.features.drawers, p.features.shelves,
                    int(p.features.wall_mounted), int(p.features.extendable),
                    int(p.features.cable_management), p.features.assembly_minutes,
                    json.dumps(p.attributes), p.care,
                    p.rating, p.reviews_count,
                    int(p.stock.in_stock), p.stock.lead_time_days,
                    p.images.main, p.product_url,
                ),
            )
        conn.commit()
        return len(catalog.products)
    finally:
        conn.close()


# ------------------------------------------------------------------ agent-facing


class SqlError(ValueError):
    """Raised when the agent's SQL is rejected or fails."""


VIEW = "catalog"


def _lock_down(conn: sqlite3.Connection) -> None:
    """Allow reads only where SQLite reports the `catalog` view as responsible.

    On a SQLITE_READ the 5th authorizer argument names the innermost view the
    access came through, or None for a direct table read. That is what stops
    `SELECT * FROM products` from bypassing the category and stock filters.
    """

    def authorizer(
        action: int,
        arg1: str | None,
        arg2: str | None,
        arg3: str | None,
        arg4: str | None,
    ) -> int:
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            # Columns of the view itself, or base-table columns reached through it.
            via_view = arg4 == VIEW
            own_column = arg1 == VIEW and arg3 == "temp"
            return sqlite3.SQLITE_OK if (via_view or own_column) else sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_DENY

    conn.set_authorizer(authorizer)


def run_sql(sql: str, category: str, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    """Run one read-only SELECT against the `catalog` view.

    `catalog` holds only in-stock products in `category`. Results are capped at
    MAX_ROWS. Anything other than a single SELECT/WITH statement is rejected.
    """
    if category not in CATEGORIES:
        raise SqlError(f"unknown category {category!r}; expected one of {sorted(CATEGORIES)}")

    statement = sql.strip().rstrip(";").strip()
    if not statement:
        raise SqlError("empty query")
    if ";" in statement:
        raise SqlError("only one statement per call")
    if not statement.lower().startswith(("select", "with")):
        raise SqlError("only SELECT (or WITH ... SELECT) queries are allowed")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        # Built before the authorizer is installed. SQLite forbids bound
        # parameters in a view body; `category` is an exact match against the
        # CATEGORIES whitelist above, so it cannot carry SQL.
        conn.execute(
            f"CREATE TEMP VIEW {VIEW} AS "
            f"SELECT * FROM products WHERE category = '{category}' AND in_stock = 1"
        )
        _lock_down(conn)
        rows = conn.execute(statement).fetchmany(MAX_ROWS)
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        raise SqlError(f"{type(exc).__name__}: {exc}") from exc
    finally:
        conn.close()


_products: dict[str, Product] | None = None


def get(product_ids: list[str]) -> list[Product]:
    """Full product records for ids the agent has settled on."""
    global _products
    if _products is None:
        _products = {p.id: p for p in load_catalog().products}
    return [_products[i] for i in product_ids if i in _products]


def categories(db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    """Category picker for the UI, with live in-stock counts."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        counts = {
            r["category"]: (r["in_stock"], r["total"])
            for r in conn.execute(
                "SELECT category, SUM(in_stock) in_stock, COUNT(*) total "
                "FROM products GROUP BY category"
            )
        }
    finally:
        conn.close()
    return [
        {"id": cid, "label": label,
         "in_stock": counts.get(cid, (0, 0))[0], "total": counts.get(cid, (0, 0))[1]}
        for cid, label in CATEGORIES.items()
    ]


if __name__ == "__main__":
    print(f"built {build()} products -> {DB_PATH}")
    for c in categories():
        print(f"  {c['id']:15} {c['label']:24} {c['in_stock']}/{c['total']} in stock")
