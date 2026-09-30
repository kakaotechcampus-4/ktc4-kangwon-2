"""Canonical Context Packet serialization and reproducibility fingerprint."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from enum import Enum

from .models import MonthlyContextPacket


def _json_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Unsupported Context value: {type(value)!r}")


def context_payload(packet: MonthlyContextPacket) -> dict[str, object]:
    payload = asdict(packet)
    if payload["safety"] is None:
        del payload["safety"]  # packets without safety placement keep their fingerprint
    return payload


def canonical_context_json(packet: MonthlyContextPacket) -> str:
    return json.dumps(
        context_payload(packet),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_value,
    )


def packet_fingerprint(packet: MonthlyContextPacket) -> str:
    return hashlib.sha256(canonical_context_json(packet).encode("utf-8")).hexdigest()
