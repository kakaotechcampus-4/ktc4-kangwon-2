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
# HUMAN_APPROVED; the institution_evidence files are corpus observations without an
# approval gate and is frozen for integrity only. A changed SHA is a different
# contract (ADR-027), so these values are never edited.
# One exception: ADR-079 (2026-11-08) re-pinned every data SHA here once after the
# institution pseudonymization overwrite. Only institution identifiers changed; the
# evidence record_ids, texts and retrieval results are identical.
FROZEN_ARTIFACTS = {
    "themes/theme_reference_v0.json": (
        "b1f181a28a5bb4c6373886a268ab2ea4282313714f38d8c1f9633498fbf9772e"
    ),
    "activities/activity_reference_v0_2.json": (
        "3cb32eb34cd8501152bd3708f1df9fb21021c7ecf2d1cf4202376364380a4ff2"
    ),
    "activities/activity_reference_v0_2_1.json": (
        "9bcdb96820911e5518c65d2f11f0ee5818c74bae5b7133b47fe9f3a985b52a06"
    ),
    "templates/monthly_template_a.json": (
        "9b4898106f6f2cb6057918fcc70af6e8c8c04aa42d4d6cfa6c15ef428405eceb"
    ),
    # Human-approved 2026-10-21 (reviewer_pm_001). ADR-027 §5: approval metadata only.
    "templates/weekly_template_a_v0_1_0.json": (
        "60330124223859623a0f35b2e56d6058994e2b86b62146b8b40474a3b72747f9"
    ),
    # Human-approved 2026-10-31 (reviewer_ai_lead_001). ADR-027 §5: approval metadata only.
    "templates/weekly_template_a_v0_2_0.json": (
        "1ec91b22d47fc04fb5f4b60f74282226dde47782141c69d6bef93d7d7c188c70"
    ),
    # Human-approved 2026-10-29 (reviewer_ai_lead_01). ADR-027 §5: approval metadata only.
    "curriculum/nuri_curriculum_content_v0_1_0_draft.json": (
        "98ed907e70fae5030721df826eec3972544e21304195703279535854714f12b2"
    ),
    # Human-approved 2026-10-29 (reviewer_ai_lead_01). ADR-027 §5: approval metadata only.
    "daily-life/daily_life_reference_v0_1_0_draft.json": (
        "2fec7d85833ac940cc46cc0bf4bf4ae2ec26cd60d89a418dedcde8649c00771c"
    ),
    "drills/emergency_drill_topics_v0_1_0_draft.json": (
        "aa0e297825f984fbdd3169732ca84766beee6d7409a1ef978f04fa7a5e636521"
    ),
    # Human-approved 2026-10-20 (reviewer_pm_001). ADR-027 §5: approval metadata only.
    "templates/monthly_template_a_v0_2_1.json": (
        "db65d4a9bca652ed5df6ecd47b969dfdce3316e2ba596125b6345e4169e4ed1d"
    ),
    # Human-approved 2026-10-31 (reviewer_ai_lead_001). ADR-050 D-3: approval metadata only.
    "templates/monthly_template_a_v0_2_2.json": (
        "95e7189f49110d6a9669d65f4d1f779b9786c0a44663bc399420b2e86be0e99b"
    ),
    # Human-approved 2026-10-31 (reviewer_ai_lead_001). Drill R-1 · R-2: approval metadata only.
    "templates/monthly_template_a_v0_2_3.json": (
        "69e2c7c813f548a74be6905d64084aaf77d3302a7d25742e19336d79aab21bd4"
    ),
    "templates/monthly_template_a_v0_2_0.json": (
        "598c7460c072c98f49beb517b2f3ccee41816c919786f2ce57c2e7373c152b78"
    ),
    "rules/safety_education_legal_v1.json": (
        "977cd3ffc04b2efb0a15d897e1d5d2099a8c5bec9c2194339ec889f564b22c45"
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
    "evidence/safety_evidence_classification_v0_2_0.json": (
        "1daa6445b7ec3f9eae958cb2f09c5da77b00a97abea7a03a0036f3e1f023d650"
    ),
    "evidence/safety_evidence_classification_v0_1_0.json": (
        "96726b66e79e7425d9a637c5ab961788c0f83179c202be54dad3bc5a407f9003"
    ),
    # Human-approved 2026-10-21 (reviewer_ai_lead_01). W3c reads it for the weekly
    # indoor_play · group_activity · indoor_alternative Sections.
    "evidence/weekly_evidence_semantic_classification_v0_1_0.json": (
        "9e4d3c7ebae2dc5fc751a5721ab3654e411a1ca8438aab6a97c96ba45f641fa8"
    ),
    "evidence/monthly_evidence_semantic_classification_v0_1_0.json": (
        "8d9930211f3cc5b993f08b263bb08266391eab686606a369f5b8e6384cb1ceaf"
    ),
    # Human-approved 2026-11-02 (reviewer_ai_lead_001): privacy exclusions, unchanged entry decisions.
    "evidence/institution_evidence_v0_2_0.json": (
        "7c051742a4e74628b8c4e2497c58e61dfa4e8399e72847a77539bfe92eeb7c98"
    ),
    "evidence/monthly_evidence_semantic_classification_v0_2_0.json": (
        "6d3702d82b2b64af6d69b7d9a0d80d51218653bc5bbf130f2a9fb13050b007a5"
    ),
    "evidence/weekly_evidence_semantic_classification_v0_2_0.json": (
        "c5e38b82c8c15f21b0e58ea6a8a52c4d9f10d7dedfc3e4bb88070291b026e19a"
    ),
    "evidence/safety_evidence_classification_v0_3_0.json": (
        "226be6158d9fca201dd1087f0de772d93ff0526d188526280c24720ba3881c18"
    ),
    "evidence/safety_reference_quality_v0_2_0.json": (
        "69ed11dcd478b29fe93944e5f6c0080af0fba5faa55dfd33eb2d432b1a53e568"
    ),
}


# Awaiting human review (ADR-027). Pinned so an unreviewed edit fails here: the
# Golden runs on these files. Only the approval commit may change them: it edits
# APPROVAL_METADATA_KEYS, removes the entry here and adds the new SHA to
# FROZEN_ARTIFACTS. PENDING_REVIEW_CONTENT proves nothing else changed.
PENDING_REVIEW_PINS = {
    "templates/monthly_template_a_v0_1_1.json": (
        "e47bce2ae40af931e44e218dde9d5e6658ede28f32aa14bf7f3eccfcd4170a83"
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
        "6c206fe2e35f8450f113ab8f5c72a18d3d8e340e65bdd10993b7f0568ff40610"
    ),
    "templates/monthly_template_a_v0_2_1.json": (
        "47c303b952368a62f1c6db31c4f6f5dd3ece93d89a3e90b7fa20ce95e2460ba6"
    ),
    "templates/monthly_template_a_v0_2_2.json": (
        "42dedfe72a8b8c62e10ab0093b4ee6025f1c07dac340aea2028a19308f4cba4c"
    ),
    "templates/monthly_template_a_v0_2_3.json": (
        "2388f6d9182f4f5b827cc624639883bbccb2fd11b77be58fda78221621b2799d"
    ),
    "templates/weekly_template_a_v0_1_0.json": (
        "8762cdadc23420795608a8b67a123306c51447f1318aa26b4ceacfbae4aa8bf8"
    ),
    "templates/weekly_template_a_v0_2_0.json": (
        "cabecd0c37bcc9ce2738e772455eaef2f8c8aec335e406ea1d14605a2e5c36ea"
    ),
    "daily-life/daily_life_reference_v0_1_0_draft.json": (
        "2ae1d32fd616409458705b6ebbfe8294cd50b733540716270309d55706fbe936"
    ),
    # Added at approval; content pin (approval metadata excluded).
    "drills/emergency_drill_topics_v0_1_0_draft.json": (
        "2d014b7682c7107de198da33d86a9b1cd6d91377820d2587d8e6ae8c95454768"
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
        catalog = repository.get_catalog("ssuksak.outdoor-activity-reference", version)
        assert catalog is not None
        assert catalog.activation_status is ActivationStatus.HUMAN_APPROVED
        assert catalog.is_active


def test_pending_templates_are_served_but_inactive():
    repository = JsonMonthlyTemplateRepository()

    # v0.2.1 was approved on 2026-10-20 (reviewer_pm_001); v0.1.1 was not. An approval
    # never carries over to another version, so v0.1.1 stays served but inactive.
    template = repository.get_template(
        "ssuksak.monthly-template-a", "monthly-template-a-v0.1.1"
    )
    assert template is not None
    assert not template.is_active
    with pytest.raises(MonthlyRuleError, match="HUMAN_APPROVED"):
        resolve_sections(template)


def test_the_approved_template_is_active_and_resolves():
    repository = JsonMonthlyTemplateRepository()

    for version in (
        "monthly-template-a-v0.2.1",
        "monthly-template-a-v0.2.2",
        "monthly-template-a-v0.2.3",
    ):
        template = repository.get_template("ssuksak.monthly-template-a", version)
        assert template is not None
        assert template.is_active
        assert resolve_sections(template)


def test_display_mode_era_templates_are_frozen_but_not_served():
    repository = JsonMonthlyTemplateRepository()

    # History only (ADR-027): still frozen above, never read on the runtime path.
    for version in ("monthly-template-a-v0.1.0", "monthly-template-a-v0.2.0"):
        assert repository.get_template("ssuksak.monthly-template-a", version) is None


@pytest.mark.parametrize(
    "legacy",
    ["templates/monthly_template_a.json", "templates/monthly_template_a_v0_2_0.json"],
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


@pytest.mark.parametrize(
    ("filename", "version", "sha", "records"),
    [
        ("institution_evidence_v0_2_0.json", "institution-evidence-ingestion-v0.2.0",
         "99260c65df0ba0d1c5d010c93a17762c3aa134ea93836e6b8e04348afe27b3ce", 12_325),
    ],
)
def test_evidence_store_identity_content_hash_and_non_normative_role_are_frozen(filename, version, sha, records):
    store = JsonInstitutionEvidenceRepository(
        DATA / "evidence" / filename, expected_content_sha256=sha
    ).get_store()

    assert store.ingestion_version == version
    assert store.schema_version == "institution-evidence.schema.v0"
    assert store.content_sha256 == sha
    assert len(store.records) == records
