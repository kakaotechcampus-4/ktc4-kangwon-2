"""In-memory test adapter for exact-version Template Profile lookup.

This adapter is not a production persistence design.
"""

from __future__ import annotations

from collections.abc import Iterable

from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.monthly_template_profile import TemplateProfile


class InMemoryTemplateProfileRepository:
    def __init__(self, profiles: Iterable[TemplateProfile] = ()) -> None:
        self._profiles: dict[tuple[str, str], TemplateProfile] = {}
        for profile in profiles:
            if not isinstance(profile, TemplateProfile):
                raise InvalidDomainValueError(
                    "InMemoryTemplateProfileRepository requires TemplateProfile values"
                )
            ref = profile.profile_ref
            key = (ref.profile_id, ref.profile_version)
            if key in self._profiles:
                raise InvalidDomainValueError(
                    "InMemoryTemplateProfileRepository contains a duplicate exact "
                    "Profile version"
                )
            self._profiles[key] = profile

    def get_profile(
        self, profile_id: str, profile_version: str
    ) -> TemplateProfile | None:
        for name, value in (
            ("profile_id", profile_id),
            ("profile_version", profile_version),
        ):
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(
                    f"InMemoryTemplateProfileRepository.{name} must be non-blank"
                )
        return self._profiles.get((profile_id, profile_version))

    def __len__(self) -> int:
        return len(self._profiles)
