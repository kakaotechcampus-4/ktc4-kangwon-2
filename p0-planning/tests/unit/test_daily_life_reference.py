from __future__ import annotations

import copy
import json

import pytest

from ssuksak.adapters.json_curriculum_reference_repository import JsonCurriculumReferenceRepository
from ssuksak.adapters.json_daily_life_reference_repository import (
    DAILY_LIFE_PATH,
    DailyLifeReferenceError,
    JsonDailyLifeReferenceRepository,
    parse_daily_life_payload,
)
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.theme_reference import ActivationStatus

ID, VERSION = "ssuksak.daily-life", "daily-life-v0.1.0"

# The sentences adopted on 2026-10-27, verbatim. A changed sentence needs a new version.
ADOPTED = (
    ("habit.01", "HABIT", "청결", "놀이한 뒤 손을 깨끗이 씻어요", "nuri2019.1.2.1"),
    ("habit.02", "HABIT", "청결", "사용한 놀잇감을 제자리에 정리해요", "nuri2019.1.2.1"),
    ("habit.04", "HABIT", "식습관", "식사 자리에 앉아 즐겁게 먹어요", "nuri2019.1.2.2"),
    ("habit.06", "HABIT", "휴식", "몸이 피곤하면 잠시 쉬어요", "nuri2019.1.2.3"),
    ("habit.10", "HABIT", "언어 예절", "친구의 이야기를 듣고 말해요", "nuri2019.2.1.5"),
    ("habit.15", "HABIT", "약속·질서", "함께 정한 놀이 약속을 지켜요", "nuri2019.3.2.6"),
    ("habit.17", "HABIT", "감정 표현", "속상한 마음을 말이나 몸짓으로 전해요", "nuri2019.3.1.2"),
    ("health.01", "HEALTH", "손 씻기", "손을 깨끗이 하는 방법을 알아봐요", "nuri2019.1.2.1"),
    ("health.02", "HEALTH", "이 닦기", "이를 깨끗이 하는 방법에 관심을 가져요", "nuri2019.1.2.1"),
    ("health.03", "HEALTH", "내 몸의 휴식", "내 몸이 쉬고 싶을 때를 알아봐요", "nuri2019.1.2.3"),
    ("health.04", "HEALTH", "날씨와 옷차림", "날씨에 맞는 옷차림을 알아봐요", "nuri2019.1.2.4"),
    ("nutrition.05", "NUTRITION", "음식에 관심 갖기", "몸에 좋은 음식에 관심을 가져요", "nuri2019.1.2.2"),
    ("nutrition.06", "NUTRITION", "즐거운 식사", "편안하고 즐겁게 식사하는 방법을 알아봐요", "nuri2019.1.2.2"),
    ("nutrition.07", "NUTRITION", "식사할 때의 자세", "식사 자리에 앉아 즐겁게 먹어요", "nuri2019.1.2.2"),
    ("nutrition.08", "NUTRITION", "다양한 음식 경험", "여러 음식에 관심을 가져요", "nuri2019.1.2.2"),
)


def _payload() -> dict:
    return json.loads(DAILY_LIFE_PATH.read_text(encoding="utf-8"))


def test_the_real_file_loads_pending_and_inactive():
    repository = JsonDailyLifeReferenceRepository()
    catalog = repository.get_catalog(ID, VERSION)

    assert catalog.activation_status is ActivationStatus.PENDING_HUMAN_REVIEW and not catalog.is_active
    assert repository.get_catalog(ID, "daily-life-v0.1.1") is None
    assert repository.get_catalog("ssuksak.daily-life-other", VERSION) is None


def test_the_real_file_holds_exactly_the_adopted_sentences():
    catalog = JsonDailyLifeReferenceRepository().get_catalog(ID, VERSION)

    assert (
        tuple((e.entry_id.removeprefix(f"{ID}."), e.kind.value, e.label, e.text, e.content_id) for e in catalog.entries)
        == ADOPTED
    )


def test_every_content_id_resolves_in_the_named_curriculum_version():
    catalog = JsonDailyLifeReferenceRepository().get_catalog(ID, VERSION)
    curriculum = JsonCurriculumReferenceRepository().get_catalog(
        catalog.curriculum_catalog_id, catalog.curriculum_catalog_version
    )

    assert curriculum is not None
    assert all(curriculum.get(e.content_id) is not None for e in catalog.entries)


def test_the_team_file_cites_no_personal_working_paths():
    text = DAILY_LIFE_PATH.read_text(encoding="utf-8")

    assert not any(marker in text for marker in ("analysis/", "handoff/", "scratch", ":/", ":\\"))


def test_an_approved_copy_is_active():
    payload = _payload()
    payload["review"].update(domain_owner_approval="HUMAN_APPROVED", runtime_active=True)

    assert parse_daily_life_payload(payload).is_active


def _set(path, value):
    def change(payload):
        target = payload
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return change


def _drop(path):
    def change(payload):
        target = payload
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]

    return change


@pytest.mark.parametrize(
    "change",
    [
        _set(("review", "domain_owner_approval"), "APPROVED"),
        _set(("review", "runtime_active"), True),  # pending but switched on
        _set(("review", "runtime_active"), "false"),
        _set(("review", "runtime_active"), 0),
        _set(("entries", 0, "kind"), "SLEEP"),
        _set(("entries", 0, "origin_refs"), []),
        _set(("entries", 0, "origin_refs", 0, "origin_id"), "unknown.origin"),
        _set(("entries", 0, "origin_refs", 0, "pages"), ""),
        _set(("origins", 1, "origin_id"), "nuri2019.notice.mohw"),
        _set(("origins", 0, "sha256"), "not-a-digest"),
        _set(("origins",), []),
        _drop(("entries", 0, "content_id")),
        _drop(("curriculum",)),
        _set(("entries",), "not a list"),
    ],
)
def test_malformed_payloads_are_rejected(change):
    payload = copy.deepcopy(_payload())
    change(payload)

    with pytest.raises(DailyLifeReferenceError):
        parse_daily_life_payload(payload)


@pytest.mark.parametrize(
    "change",
    [
        _set(("entries", 1, "entry_id"), f"{ID}.habit.01"),
        _set(("entries", 0, "text"), "  "),
        _set(("entries",), []),
    ],
)
def test_domain_rules_still_apply(change):
    payload = copy.deepcopy(_payload())
    change(payload)

    with pytest.raises(InvalidDomainValueError):
        parse_daily_life_payload(payload)


def test_two_files_with_one_version_are_refused_not_ordered():
    with pytest.raises(DailyLifeReferenceError):
        JsonDailyLifeReferenceRepository(paths=(DAILY_LIFE_PATH, DAILY_LIFE_PATH))
