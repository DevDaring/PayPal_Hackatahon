"""Canonical purchase snapshot hashing. Approval binds to this hash, not to a UI view."""

from __future__ import annotations

import hashlib
import json


def canonical_json(snapshot: dict) -> str:
    def reject_float(o):
        raise TypeError(f"non-canonical value in snapshot: {type(o).__name__}")

    def walk(v):
        if isinstance(v, float):
            raise TypeError("floats are not allowed in a purchase snapshot")
        if isinstance(v, dict):
            return {str(k): walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v

    return json.dumps(walk(snapshot), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=reject_float)


def snapshot_hash(snapshot: dict) -> str:
    return hashlib.sha256(canonical_json(snapshot).encode("utf-8")).hexdigest()


def diff(old: dict, new: dict, prefix: str = "") -> list[dict]:
    """Field-level differences between two snapshots, for explaining a blocked execution."""
    out: list[dict] = []
    for k in sorted(set(old) | set(new)):
        path = f"{prefix}{k}"
        a, b = old.get(k), new.get(k)
        if isinstance(a, dict) and isinstance(b, dict):
            out.extend(diff(a, b, path + "."))
        elif a != b:
            out.append({"field": path, "approved": a, "current": b})
    return out
