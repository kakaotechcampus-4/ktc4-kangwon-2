from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ssuksak.adapters.institution_evidence_repository import (
    JsonInstitutionEvidenceRepository,
)
from ssuksak.adapters.json_activity_reference_repository import (
    JsonActivityReferenceRepository,
)
from ssuksak.adapters.json_theme_reference_repository import (
    JsonThemeReferenceRepository,
)
from ssuksak.adapters.monthly_reference_repositories import (
    JsonMonthlyTemplateRepository,
    JsonSafetyLegalRuleRepository,
)
from ssuksak.planning.domain.theme_reference import ActivationStatus

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

FROZEN_ARTIFACTS = {
    "themes/theme_reference_v0.json": (
        "dae9f62db452c56b3b529aaa8e620411e9c11a2072163d6f9cc2a9d2ebc4d902"
    ),
    "activities/activity_reference_v0_2.json": (
        "e27ebca3342a84327c6624c5ba258b9bc98aef37ba5362b61f283c47ece0bde6"
    ),
    "activities/activity_reference_v0_2_1.json": (
        "fa9f3215c3af212ea727835c5ab06ef903b0d7ee5c1f0c615d5eaf4bc156da1a"
    ),
    "templates/monthly_template_a.json": (
        "a65b5f7355a4ac86f33d0973f1c94f8237434dc03fe593cad28aa0388cab2aaf"
    ),
    "templates/monthly_template_a_v0_2_0.json": (
        "fcde73aee479dfe020a966a5e69b06b4a6829f2d4f51217a39762eeabe707de9"
    ),
    "rules/safety_education_legal_v1.json": (
        "bd5c04864eb4eca66e51c24d58224723dbb401ead1b72f5e3b09d3a32057b3e9"
    ),
    "rules/safety_placement_policy_v2.json": (
        "52b3dff8ef2015493010e31cac01dcd6955824e8c1d9ab8521c3b172298fe75a"
    ),
    "rules/safety_placement_policy_v1.json": (
        "f65bcfee463fb8d7ed1da9bc390f7d211249f4d82464af2c258e019729bc616e"
    ),
    "evidence/institution_evidence_v0_1_0.json": (
        "8479c0490a002d9336688c1b6cacf47f2d2c083201b15df01258336c07e0ba1a"
    ),
    "evidence/monthly_evidence_semantic_classification_v0_1_0.json": (
        "8d9930211f3cc5b993f08b263bb08266391eab686606a369f5b8e6384cb1ceaf"
    ),
}


@pytest.mark.parametrize("relative,expected", sorted(FROZEN_ARTIFACTS.items()))
def test_frozen_artifact_has_canonical_lf_bytes(relative, expected):
    raw = (DATA / relative).read_bytes()

    assert b"\r" not in raw
    assert raw.endswith(b"\n")
    assert hashlib.sha256(raw).hexdigest() == expected


def test_theme_reference_exact_version_and_approval_are_frozen():
    catalog = JsonThemeReferenceRepository().get_catalog(
        "ssuksak.yearly-theme-reference", "theme-reference-v0.1.2"
    )

    assert catalog is not None
    assert catalog.activation_status is ActivationStatus.HUMAN_APPROVED
    assert catalog.is_active


def test_activity_reference_exact_versions_and_approval_are_frozen():
    repository = JsonActivityReferenceRepository()

    for version in ("activity-reference-v0.2.0", "activity-reference-v0.2.1"):
        catalog = repository.get_catalog(
            "ssuksak.outdoor-activity-reference", version
        )
        assert catalog is not None
        assert catalog.activation_status is ActivationStatus.HUMAN_APPROVED
        assert catalog.is_active


def test_template_exact_versions_and_approval_are_frozen():
    repository = JsonMonthlyTemplateRepository()

    for version in ("monthly-template-a-v0.1.0", "monthly-template-a-v0.2.0"):
        template = repository.get_template("ssuksak.monthly-template-a", version)
        assert template is not None
        assert template.is_active


def test_safety_reference_exact_version_and_six_categories_are_frozen():
    rule = JsonSafetyLegalRuleRepository().get_legal_rule(
        "child-welfare-act-decree-annex6-2022-06-21"
    )

    assert rule is not None
    assert rule.is_active
    assert len(rule.categories) == 6
    assert not rule.has_placement_policy


def test_evidence_store_identity_content_hash_and_non_normative_role_are_frozen():
    store = JsonInstitutionEvidenceRepository(
        expected_content_sha256=(
            "52b409557d3503422aa0109664298976bd7f831ed18304b818aaad936916e5ea"
        )
    ).get_store()

    assert store.ingestion_version == "institution-evidence-ingestion-v0.1.0"
    assert store.schema_version == "institution-evidence.schema.v0"
    assert store.content_sha256 == (
        "52b409557d3503422aa0109664298976bd7f831ed18304b818aaad936916e5ea"
    )
    assert len(store.records) == 12_367
