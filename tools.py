"""Tools the agents call.

`analyze_room` is a tool rather than a subagent, but not for the reason you might
expect. Passing the image *path* to a subagent works fine: with a
`FilesystemBackend` the subagent can call `read_file`, and deepagents returns
real multimodal content blocks for `.jpg`/`.png`, gated only by the model profile
(a missing profile field counts as supported).

The blocker is the model, not the architecture. `read_file` delivers the image
inside a **ToolMessage**, and gemma-4-26b rejects that:

    image in a user message  -> OK
    image in a tool message  -> 400 "invalid media input"   (OpenRouter/Darkbloom)
                             -> 500 "Failed to apply prompt replacement
                                     for mm_items['image'][0]"  (HF router)

Both providers, same result. So the image is put in a user message here, which
every vision model accepts. If you later move to an analyzer model that accepts
images in tool messages, this tool can be replaced by a proper `room_analyzer`
subagent holding `read_file`, and the orchestrator would pass it the path.
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.tools import tool

import db
from llm import chat, image_data_uri
from models import RoomAnalysis

ANALYZER_PROMPT = """You are looking at a photograph of a room in someone's home.

Report only what you can see. Do not recommend furniture, do not suggest what to
buy, and do not describe what the room "should" be - another agent does that.

Be specific about materials and colour. "Pale honey-coloured oak floorboards" is
useful; "wooden floor" is not. Name the actual hues you see rather than generic
labels.

Never estimate sizes, distances or dimensions in centimetres or inches. If a
fixed feature affects where furniture could go - a radiator, a door swing, a
sloped ceiling - describe it in words without measuring it.

Separate what is structural from what is decoration: a single houseplant is not
a green colour scheme.

Set `confidence` honestly. A dim, cluttered or partial photograph deserves a low
value, and saying so is more useful than a confident guess."""


@tool
def analyze_room(image_path: str, category: str) -> str:
    """Look at a photo of a room and describe what is in it.

    Call this once, first, before anything else. Returns the room's type, a
    visual description, existing furniture, palette, style, gaps and fixed
    features - observation only, no recommendations.

    Args:
        image_path: Path to the uploaded room photograph.
        category: The product category the shopper chose, for context only.
    """
    path = Path(image_path)
    if not path.exists():
        return f"ERROR: no image at {image_path}"
    if category not in db.CATEGORIES:
        return f"ERROR: unknown category {category!r}; expected one of {sorted(db.CATEGORIES)}"

    # json_schema, not the default: function_calling silently drops list fields
    # on this model and json_mode does not hold the shape at all.
    model = chat("analyzer").with_structured_output(RoomAnalysis, method="json_schema")
    try:
        analysis: RoomAnalysis = model.invoke([
            {"role": "system", "content": ANALYZER_PROMPT},
            {"role": "user", "content": [
                {"type": "text",
                 "text": f"Analyse this room. The shopper is shopping for: "
                         f"{db.CATEGORIES[category]}."},
                {"type": "image_url", "image_url": {"url": image_data_uri(path)}},
            ]},
        ])
    except Exception as exc:  # noqa: BLE001 - surfaced to the agent, not raised
        return f"ERROR: the vision model failed ({type(exc).__name__}: {exc})"

    return _format_analysis(analysis)


def _format_analysis(a: RoomAnalysis) -> str:
    def block(title: str, items: list[str]) -> str:
        return f"{title}:\n" + ("\n".join(f"  - {i}" for i in items) if items else "  (none)")

    return "\n".join([
        f"ROOM TYPE: {a.room_type}",
        f"CONFIDENCE: {a.confidence:.2f}",
        "",
        f"VISUAL DESCRIPTION:\n  {a.visual_description}",
        "",
        f"STYLE READ:\n  {a.style_read or '(none given)'}",
        "",
        block("EXISTING FURNITURE", a.existing_furniture),
        "",
        block("PALETTE", a.palette),
        "",
        block("GAPS", a.gaps),
        "",
        block("FIXED FEATURES", a.spatial_constraints),
    ])


@tool
def search_catalog(sql: str, category: str) -> str:
    """Run one read-only SELECT against the product catalog.

    The only readable relation is `catalog`, already filtered to `category` and to
    in-stock products. Consult the search-products skill for the columns, the
    exact vocabulary stored in each one, and how to build the query.

    Args:
        sql: A single SELECT (or WITH ... SELECT) statement querying `catalog`.
        category: The category the shopper chose.
    """
    try:
        rows = db.run_sql(sql, category)
    except db.SqlError as exc:
        return f"QUERY REJECTED: {exc}\n\nFix the SQL and try again."

    if not rows:
        return (
            "0 rows.\n\nThe filters were too tight for this category - it holds "
            "only a handful of in-stock products. Widen the query: drop the most "
            "restrictive group (usually materials, then colours) and keep style."
        )

    header = f"{len(rows)} row(s):\n"
    return header + "\n".join(
        "\n".join(f"  {k}: {v}" for k, v in row.items() if v not in (None, "", 0))
        + "\n" for row in rows
    )


@tool
def get_product_details(product_ids: list[str]) -> str:
    """Full records for products you have already found, to write reasons from.

    Use after a search, when you need the long description, care notes, delivery
    lead time or category-specific attributes for the products you are ranking.

    Args:
        product_ids: Product ids such as ["CN-001", "CN-004"].
    """
    products = db.get(product_ids)
    if not products:
        return f"No products found for {product_ids}. Only use ids returned by a search."

    out = []
    for p in products:
        out.append("\n".join([
            f"{p.id}  {p.name}  ({p.brand})  {p.price.effective:g} EUR",
            f"  {p.description}",
            f"  materials: {', '.join(p.materials)}   finish: {p.finish}",
            f"  colours: {', '.join(c.name for c in p.colors)}",
            f"  styles: {', '.join(p.styles)}",
            f"  storage: {p.storage_type}   assembly: {p.features.assembly_minutes} min",
            f"  care: {p.care}",
            f"  attributes: {json.dumps(p.attributes)}",
            f"  rating: {p.rating} from {p.reviews_count} reviews",
            f"  delivery: {p.stock.lead_time_days} days",
            f"  url: {p.product_url}",
        ]))
    return "\n\n".join(out)


CATALOG_TOOLS = [search_catalog, get_product_details]
ALL_TOOLS = [analyze_room, *CATALOG_TOOLS]
