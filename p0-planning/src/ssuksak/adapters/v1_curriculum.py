"""The approved curriculum context shared by v1 annual, monthly and weekly."""

from .json_curriculum_reference_repository import JsonCurriculumReferenceRepository
from ..planning.domain.errors import InvalidDomainValueError

CURRICULUM_CATALOG = (
    "ssuksak.nuri-curriculum-content",
    "nuri-curriculum-content-v0.1.0",
)


def v1_curriculum_catalog():
    catalog = JsonCurriculumReferenceRepository().get_catalog(*CURRICULUM_CATALOG)
    if catalog is None or not catalog.is_active:
        raise InvalidDomainValueError(
            "v1 curriculum Catalog is unavailable or not approved"
        )
    return catalog
