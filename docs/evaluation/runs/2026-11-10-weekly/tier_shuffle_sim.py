"""주간 후보 근거: 같은 연령 등급 안에서만 섞기(b) 시뮬레이션 — LLM 호출 없음 (2026-11-10).

후보 10건 중 「요청 연령과 정확히 같은 기록」(단일연령 · 혼합반이면 요청 연령 중 하나) 비율.
  고정    seed 없음 — 상위 10건 (11-09 이전 동작)
  섞기    상위 20건에서 무작위 10건 (f978b7eb)
  등급    실행하는 코드의 지금 동작. 30d8327d = 연령 등급 우선 (tier_shuffle_sim.md),
          03f3cb5a 이후 = 상위 20건에서 종류 순환 (final_shuffle_sim.md)
seed 0..49 평균. 다양성은 seed 끼리 뽑힌 근거가 겹치는 비율(낮을수록 다양).
실행: p0-planning 에서 PYTHONPATH=src python -X utf8 <this>
"""
import collections
import itertools
import random
import statistics

from ssuksak.adapters.institution_evidence_repository import JsonInstitutionEvidenceRepository
from ssuksak.adapters.weekly_evidence_classification_repository import (
    JsonWeeklyEvidenceClassificationRepository,
)
from ssuksak.planning.evidence.weekly_classification import WeeklySemanticClass
from ssuksak.planning.retrieval.models import AgeMatchKind
from ssuksak.planning.retrieval.weekly import activity_type, indoor_play_type, weekly_section_evidence

store = JsonInstitutionEvidenceRepository().get_store()
classification = JsonWeeklyEvidenceClassificationRepository().get_classification()
MONTHS = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2)
AGES = ({3}, {4}, {5}, {3, 4}, {4, 5})
SEEDS = range(50)
EXACT = {AgeMatchKind.SINGLE_AGE_EXACT, AgeMatchKind.SINGLE_AGE_IN_REQUEST}


def share(items):
    return sum(i.trace.age_match in EXACT for i in items) / len(items) if items else 0.0


def kinds(items, cls):
    f = indoor_play_type if cls is WeeklySemanticClass.INDOOR_PLAY else activity_type
    return len({f(i.record) for i in items})


def overlap(picks):
    pairs = [len(set(a) & set(b)) / max(len(a), 1) for a, b in itertools.combinations(picks, 2)]
    return statistics.mean(pairs) if pairs else 0.0


rows = collections.defaultdict(list)
for cls in (WeeklySemanticClass.GROUP_ACTIVITY, WeeklySemanticClass.INDOOR_PLAY):
    for ages in AGES:
        for month in MONTHS:
            themes = collections.Counter(r.monthly_theme for r in store.by_month(month) if r.monthly_theme)
            theme = themes.most_common(1)[0][0] if themes else ""
            kw = dict(weekly_class=cls, calendar_month=month, ages=frozenset(ages), query_text=theme, by_activity_type=True)
            fixed = weekly_section_evidence(store, classification, **kw)
            if len(fixed) < 10:
                continue
            pool = weekly_section_evidence(store, classification, top_k=20, **kw)
            old = []
            for s in SEEDS:
                keep = set(random.Random(f"{s}:{cls.value}").sample(range(len(pool)), min(10, len(pool))))
                old.append(tuple(p for i, p in enumerate(pool) if i in keep))
            new = [weekly_section_evidence(store, classification, sample_seed=s, **kw) for s in SEEDS]
            rows[(cls.name, "+".join(map(str, sorted(ages))))].append((
                month,
                share(fixed),
                statistics.mean(map(share, old)),
                statistics.mean(map(share, new)),
                overlap([[i.record_id for i in p] for p in old]),
                overlap([[i.record_id for i in p] for p in new]),
                kinds(fixed, cls),
                statistics.mean(kinds(p, cls) for p in old),
                statistics.mean(kinds(p, cls) for p in new),
            ))

print("| 칸 | 연령 | 달 수 | 정확 연령 비율 고정 / 섞기 / 등급 | seed 끼리 겹침 섞기 / 등급 | 활동 종류 수 고정 / 섞기 / 등급 | 등급 < 고정인 달 |")
print("|---|---|---|---|---|---|---|")
for (cls, ages), items in rows.items():
    m = lambda k: statistics.mean(r[k] for r in items)  # noqa: E731
    worse = sum(r[3] + 1e-9 < r[1] for r in items)
    print(f"| {cls} | 만{ages} | {len(items)} | {m(1):.2f} / {m(2):.2f} / {m(3):.2f} | {m(4):.2f} / {m(5):.2f} | {m(6):.1f} / {m(7):.1f} / {m(8):.1f} | {worse} |")

print()
print("만5 · 12월 실내놀이:", [r for r in rows[("INDOOR_PLAY", "5")] if r[0] == 12])
