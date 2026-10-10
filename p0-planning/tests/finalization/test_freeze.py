from __future__ import annotations

import hashlib
import json
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
from ssuksak.adapters.monthly_template_schema import (
    MonthlyTemplateSchemaError,
    parse_monthly_template_payload,
)
from ssuksak.planning.domain.theme_reference import ActivationStatus
from ssuksak.planning.rules.errors import MonthlyRuleError
from ssuksak.planning.rules.monthly_template_resolver import resolve_sections

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

# Content that never changes again. Every entry with a `review` approval block is
# HUMAN_APPROVED; institution_evidence_v0_1_0 is a corpus observation without an
# approval gate and is frozen for integrity only. A changed SHA is a different
# contract (ADR-027), so these values are never edited.
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
    "evidence/safety_reference_quality_v0_1_0.json": (
        "0b8a911267534516506a3d6e44dd76216ee560093ef9af3fd6bc75d8061ee8c8"
    ),
    "rules/safety_placement_policy_v1.json": (
        "f65bcfee463fb8d7ed1da9bc390f7d211249f4d82464af2c258e019729bc616e"
    ),
    "evidence/institution_evidence_v0_1_0.json": (
        "8479c0490a002d9336688c1b6cacf47f2d2c083201b15df01258336c07e0ba1a"
    ),
    "evidence/safety_evidence_classification_v0_2_0.json": (
        "1daa6445b7ec3f9eae958cb2f09c5da77b00a97abea7a03a0036f3e1f023d650"
    ),
    "evidence/safety_evidence_classification_v0_1_0.json": (
        "96726b66e79e7425d9a637c5ab961788c0f83179c202be54dad3bc5a407f9003"
    ),
    "evidence/monthly_evidence_semantic_classification_v0_1_0.json": (
        "8d9930211f3cc5b993f08b263bb08266391eab686606a369f5b8e6384cb1ceaf"
    ),
}


# Awaiting human review (ADR-027). Pinned so an unreviewed edit fails here: the
# Golden runs on these files. Only the approval commit may change them: it edits
# APPROVAL_METADATA_KEYS, removes the entry here and adds the new SHA to
# FROZEN_ARTIFACTS. PENDING_REVIEW_CONTENT proves nothing else changed.
PENDING_REVIEW_PINS = {
    "templates/monthly_template_a_v0_1_1.json": (
        "26509d5fb4986ed66e90e9003cb88ad5a1c21f3f319b6d0c7e1b65c6ec152166"
    ),
    "templates/monthly_template_a_v0_2_1.json": (
        "13e2f48db27f356db5acaaa6e2649c82abdc375402b37433f2e5b841eb77ace7"
    ),
}

# What a human approval may change inside `review`. Everything else is content.
APPROVAL_METADATA_KEYS = frozenset(
    {
        "domain_owner_approval",
        "approved_by",
        "approved_at",
        "runtime_active",
        "runtime_active_note",
    }
)

# SHA of each reviewed file without APPROVAL_METADATA_KEYS. It stays valid across
# the approval commit, so approving cannot hide a content edit. Keep the entry
# after approval.
PENDING_REVIEW_CONTENT = {
    "templates/monthly_template_a_v0_1_1.json": (
        "5fa724581a3c6dc24563de5c4bbe352f659fe5a751c1b795394bf6058388c62b"
    ),
    "templates/monthly_template_a_v0_2_1.json": (
        "b01da9b746390f9833366de83d56e4fcd3f856a70326266cf83c962c8e39452e"
    ),
}


def _content_sha(relative: str) -> str:
    payload = json.loads((DATA / relative).read_text(encoding="utf-8"))
    review = {
        key: value
        for key, value in payload["review"].items()
        if key not in APPROVAL_METADATA_KEYS
    }
    canonical = json.dumps(
        {**payload, "review": review},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@pytest.mark.parametrize(
    "relative,expected",
    sorted({**FROZEN_ARTIFACTS, **PENDING_REVIEW_PINS}.items()),
)
def test_pinned_artifact_has_canonical_lf_bytes(relative, expected):
    raw = (DATA / relative).read_bytes()

    assert b"\r" not in raw
    assert raw.endswith(b"\n")
    assert hashlib.sha256(raw).hexdigest() == expected


def test_frozen_and_pending_lists_do_not_overlap():
    assert not FROZEN_ARTIFACTS.keys() & PENDING_REVIEW_PINS.keys()


def test_every_template_file_is_frozen_or_pending():
    files = {f"templates/{path.name}" for path in (DATA / "templates").glob("*.json")}

    assert files == {
        relative
        for relative in {**FROZEN_ARTIFACTS, **PENDING_REVIEW_PINS}
        if relative.startswith("templates/")
    }


@pytest.mark.parametrize("relative", sorted(FROZEN_ARTIFACTS))
def test_frozen_artifact_with_review_is_human_approved(relative):
    review = json.loads((DATA / relative).read_text(encoding="utf-8")).get("review")

    if review is not None:
        assert review["domain_owner_approval"] == "HUMAN_APPROVED"
        assert review["approved_by"]
        assert review["approved_at"]


@pytest.mark.parametrize("relative", sorted(PENDING_REVIEW_PINS))
def test_pending_pin_is_pending_human_review(relative):
    review = json.loads((DATA / relative).read_text(encoding="utf-8"))["review"]

    assert review["domain_owner_approval"] == "PENDING_HUMAN_REVIEW"
    assert review["approved_by"] is None
    assert review["approved_at"] is None
    assert review["runtime_active"] is False


def test_every_pending_pin_has_a_content_pin():
    assert PENDING_REVIEW_PINS.keys() <= PENDING_REVIEW_CONTENT.keys()


@pytest.mark.parametrize("relative,expected", sorted(PENDING_REVIEW_CONTENT.items()))
def test_reviewed_content_is_unchanged_apart_from_approval_metadata(relative, expected):
    assert _content_sha(relative) == expected


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


def test_pending_templates_are_served_but_inactive():
    repository = JsonMonthlyTemplateRepository()

    # Republished with repeat_by, awaiting human review: served, never active (ADR-027).
    for version in ("monthly-template-a-v0.1.1", "monthly-template-a-v0.2.1"):
        template = repository.get_template("ssuksak.monthly-template-a", version)
        assert template is not None
        assert not template.is_active
        with pytest.raises(MonthlyRuleError, match="HUMAN_APPROVED"):
            resolve_sections(template)


def test_display_mode_era_templates_are_frozen_but_not_served():
    repository = JsonMonthlyTemplateRepository()

    # History only (ADR-027): still frozen above, never read on the runtime path.
    for version in ("monthly-template-a-v0.1.0", "monthly-template-a-v0.2.0"):
        assert repository.get_template("ssuksak.monthly-template-a", version) is None


@pytest.mark.parametrize(
    "legacy", ["templates/monthly_template_a.json", "templates/monthly_template_a_v0_2_0.json"]
)
def test_display_mode_template_files_are_rejected_not_translated(legacy):
    payload = json.loads((DATA / legacy).read_text(encoding="utf-8"))

    with pytest.raises(MonthlyTemplateSchemaError, match="repeat_by"):
        parse_monthly_template_payload(payload)


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
