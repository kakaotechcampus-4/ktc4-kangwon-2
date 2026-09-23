from __future__ import annotations

import collections
import copy
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from ssuksak.adapters.evidence_classification_repository import (
    DEFAULT_CLASSIFICATION_PATH,
    EvidenceClassificationError,
    JsonEvidenceClassificationRepository,
    load_evidence_classification_from_dict,
)
from ssuksak.adapters.institution_evidence_repository import (
    JsonInstitutionEvidenceRepository,
)
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.monthly_template import (
    SectionRole,
    SemanticVariant,
    TemplateSection,
)
from ssuksak.planning.evidence.classification import (
    EvidenceSemanticClassification,
    SemanticClass,
    grounding_class_for,
)
from ssuksak.planning.evidence.models import SourceSection

RAW = json.loads(DEFAULT_CLASSIFICATION_PATH.read_text(encoding="utf-8"))
STORE = JsonInstitutionEvidenceRepository().get_store()
CLASSIFICATION = JsonEvidenceClassificationRepository().get_classification()
W = SourceSection.WEEK_EXPERIENCE
D = SourceSection.DAILY_ROUTINE

# The 13 ambiguous labels, decided by the human reviewer on 2026-09-23.
HUMAN_DECISIONS = {
    (W, "환경구성 및 예상놀이계획"): SemanticClass.EXCLUDED,
    (W, "기대되는"): SemanticClass.EXCLUDED,
    (W, "주제 선정 배경"): SemanticClass.GOALS,
    (W, "예상 놀이흐름"): SemanticClass.EXCLUDED,
    (W, "흥미 예상 놀이"): SemanticClass.EXPECTED_PLAY,
    (W, "예상 놀이"): SemanticClass.EXCLUDED,
    (W, "활 동 목 표 교실을 둘러보며 새로운 환경에 관심을 가진다."): SemanticClass.EXCLUDED,
    (
        W,
        "활 동 목 표 새로운 우리 원과 반에 관심을 갖고 우리 원에서 함께 생활하는 사람들을 알아본다.",
    ): SemanticClass.EXCLUDED,
    (D, "[기본생활]"): SemanticClass.EXCLUDED,
    (D, "인성교육 기본생활습관 연계"): SemanticClass.EXCLUDED,
    (D, "기본생활 (건강·영양)"): SemanticClass.BASIC_HABIT,
    (D, "활 기본생활습관"): SemanticClass.EXCLUDED,
    (D, "생 활 기본생활습관"): SemanticClass.EXCLUDED,
}


def _records(section: SourceSection, label: str):
    return [
        record
        for record in STORE.records
        if record.source_section is section and record.source_label == label
    ]


def test_artifact_identity_and_human_approval():
    review = RAW["review"]
    approved_at = datetime.fromisoformat(review["approved_at"])

    assert RAW["schema_version"] == "monthly-evidence-semantic-classification.schema.v0"
    assert RAW["classification_version"] == "monthly-evidence-semantic-classification-v0.1.0"
    assert review["domain_owner_approval"] == "HUMAN_APPROVED"
    assert review["approved_by"] == "reviewer_ai_lead_01"
    assert "runtime_active" not in review
    assert approved_at.utcoffset() == timedelta(hours=9)
    assert approved_at <= datetime.now(timezone.utc)
    assert RAW["evidence_store"]["normative_status"] == "CORPUS_OBSERVATION_NON_NORMATIVE"


def test_approved_class_counts_over_all_exact_labels():
    labels = {
        (record.source_section, record.source_label)
        for record in STORE.records
        if record.source_section in {W, D}
    }
    by_class = collections.Counter(
        CLASSIFICATION.class_of(_records(section, label)[0])
        for section, label in labels
    )

    assert len(CLASSIFICATION.entries) == 16
    assert by_class == {
        SemanticClass.GOALS: 7,
        SemanticClass.BASIC_HABIT: 4,
        SemanticClass.SUBTHEME: 2,
        SemanticClass.EXPECTED_PLAY: 3,
        SemanticClass.EXCLUDED: 71,
    }


@pytest.mark.parametrize(("key", "expected"), sorted(HUMAN_DECISIONS.items()))
def test_ambiguous_label_human_decisions_are_applied_exactly(key, expected):
    records = _records(*key)

    assert records
    assert {CLASSIFICATION.class_of(record) for record in records} == {expected}


def test_classification_is_bound_to_the_frozen_corpus_content():
    CLASSIFICATION.require_bound_to(STORE.content_sha256)

    with pytest.raises(InvalidDomainValueError, match="different Evidence Store"):
        CLASSIFICATION.require_bound_to("0" * 64)


def test_matching_is_exact_per_section_with_excluded_default():
    subtheme = _records(W, "소주제")[0]

    assert CLASSIFICATION.class_of(subtheme) is SemanticClass.SUBTHEME
    for label in ("소주제 ", "소주제들", "예상놀이주제", "주제", "처음 보는 label"):
        assert CLASSIFICATION.class_of(replace(subtheme, source_label=label)) is SemanticClass.EXCLUDED
    assert CLASSIFICATION.class_of(replace(subtheme, source_section=D)) is SemanticClass.EXCLUDED
    same_label_other_section = _records(SourceSection.INDOOR_ALTERNATIVE, "흥미 예상 놀이")
    assert same_label_other_section
    assert all(
        CLASSIFICATION.class_of(record) is SemanticClass.EXCLUDED
        for record in same_label_other_section
    )


def _set(path, value):
    def mutate(payload):
        target = payload
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return mutate


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_set(("review", "domain_owner_approval"), "PENDING_HUMAN_REVIEW"), "not HUMAN_APPROVED"),
        (_set(("review", "runtime_active"), True), "runtime activation"),
        (_set(("review", "approved_at"), "2026-09-23T23:00:00"), "timezone-aware"),
        (_set(("matching",), "SUBSTRING"), "exact"),
        (_set(("default_class",), "GOALS"), "default_class"),
        (_set(("grounding_scope", "GOALS", "section_key"), "focus"), "grounding_scope"),
        (_set(("schema_version",), "other.schema.v0"), "schema version"),
        (_set(("evidence_store", "normative_status"), "HUMAN_APPROVED"), "unexpected Evidence Store"),
        (_set(("unexpected",), True), "root fields"),
        (
            lambda payload: payload["entries"].append(
                {"source_section": "daily_routine", "source_label": "등원", "semantic_class": "EXCLUDED"}
            ),
            "EXCLUDED is the default",
        ),
        (lambda payload: payload["entries"].append(dict(payload["entries"][0])), "duplicated"),
    ],
)
def test_loader_fails_closed_on_unapproved_or_altered_artifacts(mutate, message):
    payload = copy.deepcopy(RAW)
    mutate(payload)

    with pytest.raises(EvidenceClassificationError, match=message):
        load_evidence_classification_from_dict(payload)


def test_domain_rejects_duplicate_and_excluded_entries():
    with pytest.raises(InvalidDomainValueError, match="duplicated"):
        EvidenceSemanticClassification(
            "v", "0" * 64, ((W, "소주제", SemanticClass.SUBTHEME), (W, "소주제", SemanticClass.GOALS))
        )
    with pytest.raises(InvalidDomainValueError, match="EXCLUDED is the default"):
        EvidenceSemanticClassification("v", "0" * 64, ((W, "소주제", SemanticClass.EXCLUDED),))


@pytest.mark.parametrize(
    ("section_key", "variant", "expected"),
    [
        ("goals", None, SemanticClass.GOALS),
        ("basic_habit", None, SemanticClass.BASIC_HABIT),
        ("focus", SemanticVariant.SUBTHEME, SemanticClass.SUBTHEME),
        ("focus", SemanticVariant.EXPECTED_PLAY, SemanticClass.EXPECTED_PLAY),
        ("focus", SemanticVariant.WEEKLY_THEME, None),
        ("outdoor_play", None, None),
        ("safety_education", None, None),
    ],
)
def test_each_class_grounds_exactly_one_section_variant(section_key, variant, expected):
    section = TemplateSection(section_key, SectionRole.CONTENT, True, semantic_variant=variant)

    assert grounding_class_for(section) is expected
