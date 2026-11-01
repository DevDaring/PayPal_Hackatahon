"""Typed purchase requirements. The confirmed version is the only one that affects eligibility."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class Criterion(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    label: str = Field(max_length=120)
    expected: str = Field(max_length=60)
    synonyms: list[str] = Field(default_factory=list, max_length=12)


class RequirementSpec(BaseModel):
    item: str = Field(min_length=2, max_length=200)
    quantity: int = Field(ge=1, le=100000)
    budget_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    budget_includes: list[str] = Field(default_factory=lambda: ["shipping", "tax"])
    deadline_days: int | None = Field(default=None, ge=0, le=365)
    deadline_date: date | None = None
    timezone: str = "Asia/Kolkata"
    mandatory: list[Criterion] = Field(default_factory=list, max_length=10)
    preferred: list[str] = Field(default_factory=list, max_length=10)
    ambiguities: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    def jsonable(self) -> dict:
        return self.model_dump(mode="json")


# Synonym tables for common attributes so deterministic matching does not depend on the model.
KNOWN_ATTRIBUTES: dict[str, dict] = {
    "connector": {"label": "Connector", "values": {"USB-C": ["usb-c", "usb type-c", "type-c", "usb c"], "USB-A": ["usb-a", "usb type-a", "usb a"], "3.5mm": ["3.5mm", "3.5 mm", "aux"], "Bluetooth": ["bluetooth", "wireless"]}},
    "microphone": {"label": "Built-in microphone", "values": {"yes": ["microphone", "mic", "boom mic", "noise-cancelling mic"], "no": ["no microphone", "without microphone"]}},
}


def criterion_for(key: str, expected: str) -> Criterion:
    info = KNOWN_ATTRIBUTES.get(key)
    synonyms = []
    if info and expected in info["values"]:
        synonyms = info["values"][expected]
    label = f"{expected} connector" if key == "connector" else (info["label"] if info else key.replace("_", " ").title())
    return Criterion(key=key, label=label, expected=expected, synonyms=synonyms or [expected.lower()])
