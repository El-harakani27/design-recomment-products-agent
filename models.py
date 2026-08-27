"""Schema for the catalog and for the data passed between agents.

Deliberately loose on vocabulary: styles, colours and materials are free text so
the vision model can describe a room in its own words. The catalog stores facts
only - which product suits which room is the agent's judgement, made at query
time against skills/search-products/SKILL.md.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- catalog


class Price(BaseModel):
    amount: float
    sale_amount: float | None = None
    on_sale: bool = False
    bucket: str

    @property
    def effective(self) -> float:
        return self.sale_amount if self.on_sale and self.sale_amount else self.amount


class Dimensions(BaseModel):
    width: float
    depth: float
    height: float


class ColorRef(BaseModel):
    name: str
    hex: str
    family: str


class Features(BaseModel):
    drawers: int = 0
    shelves: int = 0
    wall_mounted: bool = False
    extendable: bool = False
    cable_management: bool = False
    assembly_required: bool = True
    assembly_minutes: int = 0


class Stock(BaseModel):
    in_stock: bool
    quantity: int
    lead_time_days: int


class Images(BaseModel):
    main: str | None = None
    gallery: list[str] = Field(default_factory=list)
    credits: list[dict[str, Any]] = Field(default_factory=list)


class Product(BaseModel):
    """Objective product facts. No recommendation logic lives here."""

    id: str
    sku: str
    name: str
    brand: str
    category: str
    short_description: str
    description: str
    price: Price
    dimensions_cm: Dimensions
    weight_kg: float
    materials: list[str]
    primary_material: str
    finish: str
    colors: list[ColorRef]
    styles: list[str]
    room_types: list[str]
    storage_type: str
    features: Features
    attributes: dict[str, Any] = Field(default_factory=dict)
    care: str
    rating: float
    reviews_count: int
    stock: Stock
    images: Images
    product_url: str
    tags: list[str] = Field(default_factory=list)


class Catalog(BaseModel):
    catalog_version: str
    currency: str
    store: str
    note: str | None = None
    products: list[Product]


# ----------------------------------------------------------------- agent interchange


class RoomAnalysis(BaseModel):
    """What room_analyzer saw. Free text on purpose - it is written by a vision
    model and read by another model, so it needs no fixed vocabulary."""

    room_type: str = Field(description="e.g. 'living room', 'narrow entryway hall'.")
    visual_description: str = Field(
        description="What the room actually looks like: light, walls, floor, mood, materials."
    )
    existing_furniture: list[str] = Field(
        default_factory=list, description="Pieces already in the photo, as observed."
    )
    palette: list[str] = Field(
        default_factory=list, description="Colours seen, in the model's own words."
    )
    style_read: str = Field(default="", description="How the model would characterise the style.")
    gaps: list[str] = Field(
        default_factory=list, description="What is visibly missing or not working."
    )
    spatial_constraints: list[str] = Field(
        default_factory=list,
        description=(
            "Fixed features that affect placement, described but never measured, "
            "e.g. 'radiator under the window', 'door opens into the corner'. "
            "Do not estimate sizes in centimetres - dimensions are out of scope."
        ),
    )
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)



class Recommendation(BaseModel):
    """One pick. `why` must be the agent's own reasoning about this room."""

    product_id: str
    rank: int
    why: str
    caveats: list[str] = Field(default_factory=list)


class RecommendationSet(BaseModel):
    room_summary: str
    recommendations: list[Recommendation]
    rejected: list[dict[str, str]] = Field(default_factory=list)
