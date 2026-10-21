from __future__ import annotations

import collections
import copy
import json

import pytest

from ssuksak.adapters.institution_evidence_repository import JsonInstitutionEvidenceRepository
from ssuksak.adapters.weekly_evidence_classification_repository import (
    DEFAULT_WEEKLY_CLASSIFICATION_PATH,
    JsonWeeklyEvidenceClassificationRepository,
    WeeklyEvidenceClassificationError,
    load_weekly_evidence_classification_from_dict,
)
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.evidence.models import SourceSection
from ssuksak.planning.evidence.weekly_classification import (
    WeeklyEvidenceClassification,
    WeeklySemanticClass,
)

RAW = json.loads(DEFAULT_WEEKLY_CLASSIFICATION_PATH.read_text(encoding="utf-8"))
CLASSIFICATION = JsonWeeklyEvidenceClassificationRepository().get_classification()


def test_the_approved_classification_loads_and_is_bound_to_the_evidence_store():
    counts = collections.Counter(weekly_class for _, _, weekly_class in CLASSIFICATION.entries)
    assert counts == {
        WeeklySemanticClass.INDOOR_PLAY: 103,
        WeeklySemanticClass.GROUP_ACTIVITY: 53,
        WeeklySemanticClass.INDOOR_ALTERNATIVE: 23,
    }
    CLASSIFICATION.require_bound_to(JsonInstitutionEvidenceRepository().get_store().content_sha256)
    with pytest.raises(InvalidDomainValueError):
        CLASSIFICATION.require_bound_to("0" * 64)


def _edited(edit):
    payload = copy.deepcopy(RAW)
    edit(payload)
    return payload


@pytest.mark.parametrize(
    "edit",
    [
        lambda p: p["review"].update(domain_owner_approval="PENDING_HUMAN_REVIEW"),
        lambda p: p["review"].update(runtime_active=True),
        lambda p: p["review"].update(approved_by="ai_lead"),
        lambda p: p["review"].update(approved_at="2026-10-21T09:51:48"),
        lambda p: p.update(schema_version="monthly-evidence-semantic-classification.schema.v0"),
        lambda p: p.update(classification_id="ssuksak.monthly-evidence-semantic-classification"),
        lambda p: p.update(matching="SUBSTRING"),
        lambda p: p.update(default_class="INDOOR_PLAY"),
        lambda p: p["grounding_scope"].update(INDOOR_PLAY={"section_key": "focus"}),
        lambda p: p["evidence_store"].update(store_id="other.store"),
        lambda p: p["entries"].append(dict(p["entries"][0])),
        lambda p: p["entries"].append({**p["entries"][0], "source_label": "새 헤더", "semantic_class": "EXCLUDED"}),
        lambda p: p["entries"].append({**p["entries"][0], "source_label": "새 헤더", "semantic_class": "GOALS"}),
        lambda p: p.pop("supersedes"),
    ],
)
def test_anything_but_the_approved_weekly_policy_is_refused(edit):
    with pytest.raises(WeeklyEvidenceClassificationError):
        load_weekly_evidence_classification_from_dict(_edited(edit))


def test_labels_match_exactly_and_unlisted_labels_are_excluded():
    classification = WeeklyEvidenceClassification(
        "weekly-classification-test",
        "a" * 64,
        ((SourceSection.INDOOR_PLAY, "쌓기", WeeklySemanticClass.INDOOR_PLAY),),
    )

    class _Record:
        def __init__(self, section, label):
            self.source_section, self.source_label = section, label

    assert classification.class_of(_Record(SourceSection.INDOOR_PLAY, "쌓기")) is WeeklySemanticClass.INDOOR_PLAY
    for section, label in [
        (SourceSection.INDOOR_PLAY, "쌓기놀이"),  # no substring match
        (SourceSection.INDOOR_PLAY, " 쌓기"),
        (SourceSection.INDOOR_ALTERNATIVE, "쌓기"),  # the section is part of the key
    ]:
        assert classification.class_of(_Record(section, label)) is WeeklySemanticClass.EXCLUDED
