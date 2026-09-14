"""Monthly LLM Planner vNext — Retriever + Monthly Context Packet (분석 전용).

Option C(Hybrid)를 구현한다.

    metadata hard filter  →  tier 배정  →  어휘 ranking  →  source diversity 제한

Vector DB를 쓰지 않는다. 현재 Evidence Store가 3.6k record 규모라 메모리 안에서
결정론적으로 처리된다. Embedding은 필요해지면 §Retrieval에서 교체 가능한
`rank()` 한 함수만 바꾸면 된다.

    python analysis/experiments/monthly_llm_vnext/retriever.py
"""

from __future__ import annotations

import collections
import dataclasses
import io
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
TMP = ROOT / "analysis" / "tmp"
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "src"))

STORE = TMP / "evidence_store.json"
CATALOG = ROOT / "data" / "activities" / "activity_reference_v0_2_1.json"

TEMPLATE_FAMILY = {"마성어린이집", "우리어린이집", "키즈로스쿨어린이집", "혜솔어린이집"}

STOP = {"놀이", "하기", "해요", "활동", "우리", "함께", "다양한", "만들기", "보기"}


def tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    raw = re.findall(r"[가-힣]{2,}", text)
    out: set[str] = set()
    for w in raw:
        out.add(w)
        for n in (2, 3):
            for i in range(len(w) - n + 1):
                out.add(w[i:i + n])
    return {w for w in out if w not in STOP}


@dataclasses.dataclass(frozen=True, slots=True)
class RetrievalQuery:
    target_month: str          # YYYY-MM
    calendar_month: int
    ages: tuple[int, ...]
    theme_id: str
    theme_label: str
    week_ids: tuple[str, ...]


@dataclasses.dataclass(slots=True)
class Block:
    name: str
    required: bool
    top_k: int
    retrieval: str
    items: list[dict]
    note: str = ""


def diversity_limit(records: list[dict], *, per_institution: int, top_k: int) -> list[dict]:
    """같은 기관이 블록을 독점하지 못하게 한다.

    Template Family는 한 Source로 묶어 센다(§13 Source Independence).
    """
    seen: collections.Counter = collections.Counter()
    out: list[dict] = []
    for r in records:
        inst = r["institution_id"] or "?"
        key = "TEMPLATE_FAMILY" if inst in TEMPLATE_FAMILY else inst
        if seen[key] >= per_institution:
            continue
        seen[key] += 1
        out.append(r)
        if len(out) >= top_k:
            break
    return out


def rank(records: list[dict], q: RetrievalQuery) -> list[dict]:
    """어휘 기반 결정론 ranking. Embedding으로 교체 가능한 지점이다."""
    qt = tokens(q.theme_label)

    def key(r: dict):
        txt = r.get("activity_text") or r.get("experience_text") or ""
        overlap = len(tokens(txt) & qt) + len(tokens(r.get("monthly_theme")) & qt)
        single = 1 if r["age_evidence_type"] == "SINGLE_AGE_PAGE" else 0
        return (-overlap, -single, r["record_id"])

    return sorted(records, key=key)


class MonthlyRetriever:
    def __init__(self, store: list[dict] | None = None) -> None:
        self.store = store if store is not None else json.loads(
            STORE.read_text("utf-8"))
        self.by_month: dict[int, list[dict]] = collections.defaultdict(list)
        for r in self.store:
            if r["machine_readability"] != "TEXT_LAYER":
                continue
            self.by_month[r["month"]].append(r)
        # 같은 문서에 서로 다른 단일연령 면이 있는지 (age contrast 후보)
        pages = collections.defaultdict(set)
        for r in self.store:
            if r["age_evidence_type"] == "SINGLE_AGE_PAGE" and r["age_scope"]:
                pages[r["sha12"]].add(r["age_scope"][0])
        self.contrast_docs = {k for k, v in pages.items() if len(v) >= 2}

    # ------------------------------------------------------------ blocks

    def institution_monthly_evidence(self, q: RetrievalQuery, top_k: int = 12) -> Block:
        pool = [r for r in self.by_month.get(q.calendar_month, [])
                if r["source_section"] in ("outdoor_play", "week_experience")
                and r["setting"] != "INDOOR_ALTERNATIVE"]
        t1 = [r for r in pool if r["age_evidence_type"] == "SINGLE_AGE_PAGE"
              and tuple(r["age_scope"]) == q.ages]
        t2 = [r for r in pool if r not in t1
              and set(q.ages) & set(r["age_scope"])]
        ordered = rank(t1, q) + rank(t2, q)
        return Block("INSTITUTION MONTHLY EVIDENCE", True, top_k,
                     "metadata hard filter(month, section, setting) + 어휘 ranking "
                     "+ 기관당 2건 상한",
                     diversity_limit(ordered, per_institution=2, top_k=top_k),
                     note=f"tier1(동월·동연령 단일) {len(t1)} / tier2(동월·연령포함) {len(t2)}")

    def age_contrast_evidence(self, q: RetrievalQuery, top_k: int = 6) -> Block:
        """같은 문서 안에 다른 단일연령 면이 함께 있는 근거만 쓴다.

        기관 차이·양식 차이에 오염되지 않은 **순수 연령 대조**다.
        """
        pool = [r for r in self.by_month.get(q.calendar_month, [])
                if r["sha12"] in self.contrast_docs
                and r["age_evidence_type"] == "SINGLE_AGE_PAGE"
                and r["source_section"] == "outdoor_play"
                and r["setting"] == "OUTDOOR"]
        by_doc: dict[str, list[dict]] = collections.defaultdict(list)
        for r in pool:
            by_doc[r["sha12"]].append(r)
        items = []
        for sha, rows in sorted(by_doc.items()):
            ages = sorted({r["age_scope"][0] for r in rows})
            if len(ages) < 2:
                continue
            for age in ages:
                first = next(r for r in rows if r["age_scope"][0] == age)
                items.append(first)
        return Block("AGE-CONTRAST EVIDENCE", False, top_k,
                     "같은 문서·같은 월·연령만 다른 면에서만 추출",
                     diversity_limit(items, per_institution=3, top_k=top_k),
                     note=f"대조 문서 {len(by_doc)}건")

    def week_experience_candidates(self, q: RetrievalQuery, top_k: int = 10) -> Block:
        pool = [r for r in self.by_month.get(q.calendar_month, [])
                if r["source_section"] == "week_experience"]
        return Block("WEEK EXPERIENCE CANDIDATES", True, top_k,
                     "month hard filter + 어휘 ranking + 기관당 2건 상한",
                     diversity_limit(rank(pool, q), per_institution=2, top_k=top_k),
                     note="원문 label 보존. **주차 번호는 부여하지 않는다** — "
                          "Corpus에 순서 근거가 없다")

    def corpus_activity_evidence(self, q: RetrievalQuery, top_k: int = 10) -> Block:
        pool = [r for r in self.by_month.get(q.calendar_month, [])
                if r["source_section"] == "outdoor_play"
                and r["setting"] == "OUTDOOR"]
        return Block("OTHER RETRIEVED ACTIVITY EVIDENCE", False, top_k,
                     "month + outdoor + OUTDOOR setting, 기관당 2건 상한",
                     diversity_limit(rank(pool, q), per_institution=2, top_k=top_k),
                     note="Activity Reference 밖의 관찰값. canonical이 아니다")


# --------------------------------------------------------- Reference block


def reference_activities(q: RetrievalQuery, top_k: int = 12) -> Block:
    """승인 Catalog에서 hard filter 후 Top-K만 넣는다. 196개 전체를 넣지 않는다."""
    from ssuksak.adapters.json_activity_reference_repository import (
        production_activity_reference_repository,
    )
    cat = production_activity_reference_repository().get_catalog(
        "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1")
    pool = cat.eligible_candidates(section_key="outdoor_play",
                                   calendar_month=q.calendar_month,
                                   ages=frozenset(q.ages))
    qt = tokens(q.theme_label)
    rows = sorted(
        pool,
        key=lambda a: (-len(tokens(a.label) & qt),
                       -a.evidence_strength_for_month(q.calendar_month),
                       1 if a.has_confirmed_display_issue else 0,
                       a.activity_id),
    )
    items = [{
        "activity_id": a.activity_id, "label": a.label,
        "evidence_strength": a.evidence_strength_for_month(q.calendar_month),
        "display_quality_issue": a.has_confirmed_display_issue,
    } for a in rows[:top_k]]
    return Block("REFERENCE ACTIVITIES", True, top_k,
                 "ActivityCatalog.eligible_candidates() hard filter "
                 "+ Rule v2 축으로 pre-ranking → Top-K",
                 items, note=f"hard filter 통과 {len(pool)} → Top {len(items)}")


def build_packet(q: RetrievalQuery, retr: MonthlyRetriever) -> list[Block]:
    return [
        retr.institution_monthly_evidence(q),
        retr.age_contrast_evidence(q),
        retr.week_experience_candidates(q),
        reference_activities(q),
        retr.corpus_activity_evidence(q),
    ]


def main() -> int:
    retr = MonthlyRetriever()
    q = RetrievalQuery("2026-07", 7, (4,), "yr_theme_summer", "여름",
                       ("2026-07-W1", "2026-07-W2", "2026-07-W3",
                        "2026-07-W4", "2026-07-W5"))
    print("=" * 92)
    print(f" Retriever 시연 — {q.target_month} 만{q.ages}세 Theme={q.theme_label}")
    print("=" * 92)
    for b in build_packet(q, retr):
        print(f"\n  [{b.name}]  required={b.required}  top_k={b.top_k}  "
              f"반환 {len(b.items)}")
        print(f"    retrieval : {b.retrieval}")
        print(f"    note      : {b.note}")
        for it in b.items[:6]:
            if "activity_id" in it:
                print(f"      · {it['label']}  (ev={it['evidence_strength']})")
            else:
                txt = it.get("activity_text") or it.get("experience_text")
                print(f"      · [{it['institution_id']}/만{it['age_scope']}세/"
                      f"{it['source_label']}] {txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
