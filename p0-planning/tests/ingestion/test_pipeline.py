"""Ingestion Pipeline · Schema · 결정론 · Artifact 회귀 (L1).

**PDF를 열지 않는다.** `SourceDocumentReader` Port에 Fake를 주입하므로 PDF
라이브러리 없이 전체 파이프라인이 돌아간다(CLAUDE.md §17 Port 우선 원칙).
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest
from pydantic import ValidationError

from ssuksak.ingestion import (
    EVIDENCE_STORE_SCHEMA_VERSION,
    INGESTION_VERSION,
    AgeEvidenceType,
    EvidenceRecord,
    EvidenceSourceType,
    ExtractionQuality,
    MachineReadability,
    ReusePolicy,
    Setting,
    SourceFile,
    SourceSection,
    ingest_corpus,
    store_payload,
)
from ssuksak.ingestion.cells import Word, build_cells
from ssuksak.ingestion.evidence_builder import make_record_id
from ssuksak.ingestion.pipeline import content_sha256

ROOT = pathlib.Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "data" / "evidence" / "institution_evidence_v0_1_0.json"


# ============================================== Fake Source

_V = [(10.0, 90.0, 240.0), (110.0, 90.0, 240.0), (300.0, 90.0, 240.0)]
_H = [(90.0, 10.0, 300.0), (140.0, 10.0, 300.0), (190.0, 10.0, 300.0),
      (240.0, 10.0, 300.0)]

_WORDS = [
    Word(12, 100, 60, 112, "생활주제"),
    Word(120, 100, 180, 112, "여름"),
    Word(12, 150, 60, 162, "바깥놀이"),
    Word(120, 150, 210, 162, "장화 신고 물웅덩이"),
    Word(120, 165, 160, 177, "건너기"),
    Word(12, 200, 60, 212, "소주제"),
    Word(120, 200, 220, 212, "여름 날씨에 관심 갖기"),
]
_TEXT = "< 7월 4세 놀이 이야기 >\n생활주제 여름  연령 4세"


class _FakeDocument:
    def __init__(self, pages: int = 1, with_cells: bool = True) -> None:
        self._pages = pages
        self._with_cells = with_cells
        self.closed = False

    @property
    def page_count(self) -> int:
        return self._pages

    def page_text(self, page: int) -> str:
        return _TEXT

    def page_cells(self, page: int, *, rejoin: bool = True):
        if not self._with_cells:
            return build_cells(page=page, words=_WORDS, vertical_rules=[],
                               horizontal_rules=[])
        return build_cells(page=page, words=_WORDS, vertical_rules=_V,
                           horizontal_rules=_H, rejoin=rejoin)

    def close(self) -> None:
        self.closed = True


class _FakeReader:
    def __init__(self, *, with_cells: bool = True, pages: int = 1) -> None:
        self.with_cells = with_cells
        self.pages = pages
        self.opened: list[str] = []

    def open(self, path: str) -> _FakeDocument:
        self.opened.append(path)
        return _FakeDocument(self.pages, self.with_cells)


def _source(readable: bool = True, name: str = "x") -> SourceFile:
    return SourceFile(
        path=f"references/samples/monthly/2026_국공립_테스트{name}어린이집_"
             f"만4세_월간계획안(7월).pdf",
        sha256=hashlib.sha256(name.encode()).hexdigest(),
        readable=readable,
    )


# ============================================== Schema


def _valid_kwargs(**over):
    base = dict(
        record_id="ev_abc_p01_r00100_c01_i01",
        source_type=EvidenceSourceType.INSTITUTION_SAMPLE,
        source_path="references/samples/monthly/x.pdf",
        source_sha256="a" * 64,
        page=1,
        age_scope=(4,),
        age_evidence_type=AgeEvidenceType.SINGLE_AGE_PAGE,
        source_section=SourceSection.OUTDOOR_PLAY,
        source_label="바깥놀이",
        setting=Setting.OUTDOOR,
        machine_readability=MachineReadability.TEXT_LAYER,
        extraction_quality=ExtractionQuality.VALID,
        extraction_method="table_line_geometry_v1",
    )
    base.update(over)
    return base


def test_record_schema_accepts_valid_payload():
    r = EvidenceRecord(**_valid_kwargs())
    assert r.reuse_policy is ReusePolicy.CONTEXT_ONLY


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        EvidenceRecord(**_valid_kwargs(totally_unknown_field=1))


def test_missing_required_field_is_rejected():
    kwargs = _valid_kwargs()
    del kwargs["setting"]
    with pytest.raises(ValidationError):
        EvidenceRecord(**kwargs)


def test_invalid_enum_is_rejected():
    with pytest.raises(ValidationError):
        EvidenceRecord(**_valid_kwargs(setting="MAYBE_OUTDOOR"))


def test_invalid_sha_is_rejected():
    with pytest.raises(ValidationError):
        EvidenceRecord(**_valid_kwargs(source_sha256="tooshort"))


def test_out_of_target_age_is_rejected():
    with pytest.raises(ValidationError):
        EvidenceRecord(**_valid_kwargs(age_scope=(1, 4)))


def test_invalid_month_is_rejected():
    with pytest.raises(ValidationError):
        EvidenceRecord(**_valid_kwargs(month=13))


def test_record_is_frozen_and_derived_fields_are_not_writable():
    r = EvidenceRecord(**_valid_kwargs())
    assert r.general_grounding_eligible is True
    with pytest.raises(ValidationError):
        r.setting = Setting.INDOOR                 # frozen
    with pytest.raises(ValidationError):
        r.general_grounding_eligible = False       # 파생값은 덮어쓸 수 없다
    with pytest.raises(ValidationError):
        EvidenceRecord(**_valid_kwargs(general_grounding_eligible=True))


def test_grounding_eligibility_is_derived_from_quality_and_readability():
    ok = EvidenceRecord(**_valid_kwargs())
    assert ok.general_grounding_eligible and ok.outdoor_activity_eligible

    broken = EvidenceRecord(
        **_valid_kwargs(extraction_quality=ExtractionQuality.INVALID)
    )
    assert not broken.general_grounding_eligible
    assert not broken.outdoor_activity_eligible

    image = EvidenceRecord(
        **_valid_kwargs(machine_readability=MachineReadability.IMAGE_ONLY)
    )
    assert not image.general_grounding_eligible


def test_indoor_alternative_is_never_outdoor_eligible():
    alt = EvidenceRecord(
        **_valid_kwargs(setting=Setting.INDOOR_ALTERNATIVE,
                        source_section=SourceSection.INDOOR_ALTERNATIVE)
    )
    assert alt.general_grounding_eligible is True
    assert alt.outdoor_activity_eligible is False


def test_single_age_property():
    assert EvidenceRecord(**_valid_kwargs()).single_age == 4
    mixed = EvidenceRecord(
        **_valid_kwargs(age_scope=(3, 4),
                        age_evidence_type=AgeEvidenceType.MIXED_AGE_PAGE)
    )
    assert mixed.single_age is None


def test_source_type_value_matches_approved_contract():
    """OD-N13에서 승인해 CLAUDE.md §13.1에 등재한 값과 문자열이 같아야 한다."""
    assert EvidenceSourceType.INSTITUTION_SAMPLE.value == "INSTITUTION_SAMPLE"
    claude_md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "\nINSTITUTION_SAMPLE\n" in claude_md


# ============================================== Pipeline


def test_pipeline_builds_records_from_cells():
    reader = _FakeReader()
    result = ingest_corpus([_source()], reader)
    assert result.files_scanned == 1
    assert result.files_text_layer == 1
    assert result.pages_with_cells == 1
    assert result.records

    outdoor = [r for r in result.records if r.outdoor_activity_eligible]
    assert [r.activity_text for r in outdoor] == ["장화 신고 물웅덩이 건너기"]


def test_pipeline_records_page_level_age():
    result = ingest_corpus([_source()], _FakeReader())
    assert {r.age_scope for r in result.records} == {(4,)}
    assert {r.age_evidence_type for r in result.records} == {
        AgeEvidenceType.SINGLE_AGE_PAGE
    }


def test_pipeline_captures_week_experience_separately():
    result = ingest_corpus([_source()], _FakeReader())
    week = [r for r in result.records
            if r.source_section is SourceSection.WEEK_EXPERIENCE]
    assert [r.experience_text for r in week] == ["여름 날씨에 관심 갖기"]
    assert all(r.activity_text is None for r in week)


def test_theme_row_becomes_context_not_a_record():
    result = ingest_corpus([_source()], _FakeReader())
    assert all(r.source_section is not SourceSection.THEME for r in result.records)
    assert {r.monthly_theme for r in result.records} == {"여름"}


def test_week_position_is_never_guessed():
    """월간 표 안의 순서를 주차로 추론하지 않는다."""
    result = ingest_corpus([_source()], _FakeReader())
    assert all(r.week_position is None for r in result.records)
    assert all(r.week_label is None for r in result.records)


def test_image_only_source_is_recorded_but_not_ingested():
    """읽을 수 없으면 추정하지 않는다. 존재는 남기고 record는 만들지 않는다."""
    reader = _FakeReader()
    result = ingest_corpus([_source(readable=False)], reader)
    assert result.files_image_only == 1
    assert result.files_text_layer == 0
    assert result.records == []
    assert reader.opened == []


def test_source_without_table_lines_is_reported_not_guessed():
    result = ingest_corpus([_source()], _FakeReader(with_cells=False))
    assert result.records == []
    assert len(result.files_without_cells) == 1


def test_reuse_policy_defaults_to_context_only():
    """P0 Corpus에는 Product Output 직접 사용이 허용된 Record가 없다."""
    result = ingest_corpus([_source()], _FakeReader())
    assert {r.reuse_policy for r in result.records} == {ReusePolicy.CONTEXT_ONLY}


# ============================================== 결정론


def test_record_id_is_derived_from_source_coordinates():
    a = make_record_id("f" * 64, 2, 150.0, 1, 3)
    b = make_record_id("f" * 64, 2, 150.4, 1, 3)
    assert a == b == "ev_ffffffffffff_p02_r00150_c01_i03"


def test_same_source_yields_identical_records():
    one = ingest_corpus([_source()], _FakeReader())
    two = ingest_corpus([_source()], _FakeReader())
    assert [r.record_id for r in one.records] == [r.record_id for r in two.records]
    assert one.records == two.records


def test_source_order_does_not_change_output():
    a = ingest_corpus([_source(name="a"), _source(name="b")], _FakeReader())
    b = ingest_corpus([_source(name="b"), _source(name="a")], _FakeReader())
    assert [r.record_id for r in a.records] == [r.record_id for r in b.records]


def test_store_payload_content_sha_is_stable():
    one = store_payload(ingest_corpus([_source()], _FakeReader()))
    two = store_payload(ingest_corpus([_source()], _FakeReader()))
    assert content_sha256(one) == content_sha256(two)


def test_store_payload_has_no_build_metadata():
    """`generated_at`이 content에 섞이면 같은 내용도 매번 SHA가 달라진다."""
    payload = store_payload(ingest_corpus([_source()], _FakeReader()))
    assert "generated_at" not in payload
    assert "build" not in payload
    assert payload["schema_version"] == EVIDENCE_STORE_SCHEMA_VERSION
    assert payload["ingestion_version"] == INGESTION_VERSION


def test_manifest_lists_every_source_including_image_only():
    payload = store_payload(
        ingest_corpus([_source(name="a"), _source(readable=False, name="b")],
                      _FakeReader())
    )
    manifest = payload["source_hash_manifest"]
    assert len(manifest) == 2
    assert {m["machine_readability"] for m in manifest} == {
        "TEXT_LAYER", "IMAGE_ONLY"
    }


# ============================================== Artifact


@pytest.mark.skipif(not ARTIFACT.exists(), reason="Evidence Store artifact 미빌드")
def test_artifact_is_a_corpus_observation_not_a_canonical_reference():
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert d["schema_version"] == EVIDENCE_STORE_SCHEMA_VERSION
    assert d["ingestion_version"] == INGESTION_VERSION
    assert d["normative_status"] == "CORPUS_OBSERVATION_NON_NORMATIVE"
    assert "HUMAN_APPROVED" not in json.dumps(d["disclaimer"], ensure_ascii=False)


@pytest.mark.skipif(not ARTIFACT.exists(), reason="Evidence Store artifact 미빌드")
def test_artifact_records_parse_under_strict_schema():
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert d["record_count"] == len(d["records"])
    for raw in d["records"][:400]:
        EvidenceRecord.model_validate(raw)


@pytest.mark.skipif(not ARTIFACT.exists(), reason="Evidence Store artifact 미빌드")
def test_artifact_has_no_guessed_week_positions():
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert not any("week_position" in r for r in d["records"])


@pytest.mark.skipif(not ARTIFACT.exists(), reason="Evidence Store artifact 미빌드")
def test_artifact_record_ids_are_unique():
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    ids = [r["record_id"] for r in d["records"]]
    assert len(ids) == len(set(ids))


@pytest.mark.skipif(not ARTIFACT.exists(), reason="Evidence Store artifact 미빌드")
def test_artifact_content_sha_matches_recorded_build_value():
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    content = {k: v for k, v in d.items() if k != "build"}
    assert content_sha256(content) == d["build"]["content_sha256"]
