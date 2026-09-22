"""Immutable indexed Institution Evidence Store."""

from __future__ import annotations

import re

from ..domain.errors import InvalidDomainValueError
from .models import EvidenceRecord

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class InstitutionEvidenceStore:
    __slots__ = ("_by_month", "_content_sha256", "_records", "_schema_version", "_version")

    def __init__(
        self,
        records: tuple[EvidenceRecord, ...],
        *,
        ingestion_version: str,
        schema_version: str,
        content_sha256: str,
    ) -> None:
        if not isinstance(records, tuple) or not all(isinstance(item, EvidenceRecord) for item in records):
            raise InvalidDomainValueError("Evidence Store records must be an EvidenceRecord tuple")
        ids = tuple(item.record_id for item in records)
        if len(set(ids)) != len(ids):
            raise InvalidDomainValueError("Evidence Store contains duplicate record ids")
        if ids != tuple(sorted(ids)):
            raise InvalidDomainValueError("Evidence Store records must use deterministic record_id order")
        for name, value in (("ingestion_version", ingestion_version), ("schema_version", schema_version)):
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(f"Evidence Store {name} must be non-blank")
        if _SHA256.fullmatch(content_sha256) is None:
            raise InvalidDomainValueError("Evidence Store content_sha256 is invalid")
        self._records = records
        self._version = ingestion_version
        self._schema_version = schema_version
        self._content_sha256 = content_sha256
        index: dict[int | None, list[EvidenceRecord]] = {}
        for record in records:
            index.setdefault(record.month, []).append(record)
        self._by_month = {month: tuple(items) for month, items in index.items()}

    @property
    def records(self) -> tuple[EvidenceRecord, ...]:
        return self._records

    @property
    def ingestion_version(self) -> str:
        return self._version

    @property
    def schema_version(self) -> str:
        return self._schema_version

    @property
    def content_sha256(self) -> str:
        return self._content_sha256

    def by_month(self, month: int) -> tuple[EvidenceRecord, ...]:
        if type(month) is not int or not 1 <= month <= 12:
            raise InvalidDomainValueError("Evidence Store month must be 1 through 12")
        return self._by_month.get(month, ())

    def __len__(self) -> int:
        return len(self._records)
