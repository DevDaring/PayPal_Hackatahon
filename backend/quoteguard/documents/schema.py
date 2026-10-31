"""Strict structured-extraction schema shared by the LLM and the deterministic extractor."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

CRITICAL_FIELDS = ("supplier_name", "currency", "quantity", "subtotal", "shipping", "tax", "total", "delivery_days", "valid_until")
MONEY_FIELDS = ("unit_price", "subtotal", "shipping", "tax", "discount", "total")


class Cited(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str | int | bool | None = None
    page: int | None = Field(default=None, ge=1, le=500)
    source_text: str | None = Field(default=None, max_length=400)

    @field_validator("value", mode="before")
    @classmethod
    def _no_float(cls, v):
        if isinstance(v, float):
            return format(v, "f")
        return v


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(max_length=300)
    quantity: int | None = None
    unit_price: str | None = None
    line_total: str | None = None


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_name: Cited = Cited()
    currency: Cited = Cited()
    currency_explicit: bool = False
    quantity: Cited = Cited()
    unit_price: Cited = Cited()
    subtotal: Cited = Cited()
    shipping: Cited = Cited()
    tax: Cited = Cited()
    discount: Cited = Cited()
    total: Cited = Cited()
    delivery_days: Cited = Cited()
    issue_date: Cited = Cited()
    valid_until: Cited = Cited()
    product_description: Cited = Cited()
    shipping_terms: Cited = Cited()
    pricing_terms: Cited = Cited()
    pricing_scales_with_quantity: bool = False
    flat_shipping: bool = False
    attributes: dict[str, Cited] = Field(default_factory=dict)
    line_items: list[LineItem] = Field(default_factory=list, max_length=50)
    ambiguities: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("attributes")
    @classmethod
    def _attr_keys(cls, v: dict) -> dict:
        if len(v) > 12:
            raise ValueError("too many attributes")
        for k in v:
            if not k.replace("_", "").isalnum() or len(k) > 40:
                raise ValueError("invalid attribute key")
        return v
