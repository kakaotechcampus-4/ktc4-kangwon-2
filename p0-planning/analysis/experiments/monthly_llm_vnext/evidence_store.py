"""Monthly LLM Planner vNext — Evidence Store Prototype (분석 전용).

Production을 수정하지 않는다. `analysis/tmp/`만 읽고 쓴다.

목적: `references/` Corpus를 **Retrieval 가능한 Evidence Record**로 만든다.
Activity Reference(canonical · HUMAN_APPROVED)와 **역할이 다르다.**

    Activity Reference   사람이 승인한 canonical 후보. Plan Item의 Evidence가 된다.
    Evidence Store       더 넓은 Corpus 관찰값. LLM Grounding Context로만 쓴다.
                         canonical일 필요가 없고 Plan Item Evidence가 되지 않는다.

    python analysis/experiments/monthly_llm_vnext/evidence_store.py
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
TEXT = TMP / "corpus_text"
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OUT = TMP / "evidence_store.json"

# ------------------------------------------------------------- Section 어휘
# 원문 label을 canonical section으로 매핑한다. **원문은 항상 함께 보존한다.**

SECTION_RULES: tuple[tuple[str, re.Pattern], ...] = (
    ("indoor_alternative", re.compile(r"(대체\s*활동|대체\s*놀이|실내\s*대체)")),
    ("outdoor_play", re.compile(r"(바\s*깥\s*놀?\s*이?|실\s*외\s*놀?\s*이?|산책|나들이|텃밭)")),
    ("theme", re.compile(r"(생활\s*주제|놀이\s*주제|예상\s*놀이\s*주제|월\s*주제|^주\s*제$)")),
    ("week_experience", re.compile(r"(소\s*주제|예상\s*놀이|기대되는|주제\s*선정|교사의\s*기대|"
                                   r"함께\s*하는\s*놀이|놀이\s*이야기|놀이\s*흐름)")),
    ("safety_education", re.compile(r"(안전\s*교육|비상\s*대응|소방|재난)")),
    ("indoor_play", re.compile(r"(실\s*내\s*놀?\s*이?|쌓기|역할|미술|언어|음률|과학)")),
    ("daily_routine", re.compile(r"(기본\s*생활|일상\s*생활|등원|전이|휴식|건강\s*영양)")),
    ("event", re.compile(r"(행사|가정과의|체험)")),
)

SETTING_BY_SECTION = {
    "outdoor_play": "OUTDOOR",
    "indoor_alternative": "INDOOR_ALTERNATIVE",
    "indoor_play": "INDOOR",
}

ROW_LABEL = re.compile(r"^\s{0,20}([가-힣][가-힣 ·/()]{0,16}?)\s{2,}(\S.*)$")
BULLET = re.compile(r"^\s*[-–—*·•⦁▸▶♥※<>\[\]]+\s*")
SPLIT = re.compile(r"[/·•⦁▸▶]|\s{3,}")
ALT_INLINE = re.compile(r"[\[【(]\s*(?:실내\s*)?대체[^\]】)]*[\]】)]")

TEMPLATE_FAMILY = {"마성어린이집", "우리어린이집", "키즈로스쿨어린이집", "혜솔어린이집"}


def canonical_section(label: str) -> str:
    t = label.strip()
    for name, pat in SECTION_RULES:
        if pat.search(t):
            return name
    return "other"


@dataclasses.dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """Retrieval 단위. **면(page) 안의 한 줄**이 기본 단위다.

    `record_id`는 (sha12, page, section, 순번)에서 결정론적으로 만든다.
    """

    record_id: str
    source_type: str            # INSTITUTION_SAMPLE | OFFICIAL_PLAY_CASE | ...
    source_path: str
    sha12: str
    page: int
    institution_id: str | None
    institution_type: str | None      # 국공립 / 민간 / 직장 ...
    year: int | None
    month: int | None
    age_scope: tuple[int, ...]
    age_evidence_type: str      # SINGLE_AGE_PAGE | MIXED_AGE_PAGE | AGE_UNKNOWN
    monthly_theme: str | None
    source_section: str         # canonical
    source_label: str           # 원문 그대로
    week_position: int | None   # 원문에 주차가 명시된 경우만. 추정하지 않는다.
    week_label: str | None
    experience_text: str | None
    activity_text: str | None
    setting: str                # OUTDOOR | INDOOR | INDOOR_ALTERNATIVE | UNKNOWN
    template_family: bool
    machine_readability: str    # TEXT_LAYER | IMAGE_ONLY
    reuse_policy: str           # CONTEXT_ONLY (P0 기본)


def build() -> list[EvidenceRecord]:
    D = json.loads((TMP / "new_reference_impact.json").read_text("utf-8"))
    out: list[EvidenceRecord] = []

    for r in D["records"]:
        if r["dir"] not in ("monthly", "weekly"):
            continue
        p = TEXT / f"{r['sha12']}.layout.txt"
        if not p.exists():
            continue
        pages = [x for x in p.read_text("utf-8", errors="replace").split("\f")
                 if x.strip()]
        readable = "TEXT_LAYER" if r["readable"] else "IMAGE_ONLY"
        inst = r["institution"]
        fam = inst in TEMPLATE_FAMILY

        for info in r["_pages"]:
            i = info["page"] - 1
            if i >= len(pages):
                continue
            txt = pages[i]
            month = r["fn_month"] or (info["months"][0] if info["months"] else None)
            ages = tuple(info["ages"])
            if info["single_age"] is not None:
                age_kind = "SINGLE_AGE_PAGE"
            elif ages:
                age_kind = "MIXED_AGE_PAGE"
            else:
                age_kind = "AGE_UNKNOWN"

            # 이 면의 monthly_theme (theme 행에서만)
            theme = None
            for ln in txt.splitlines():
                m = ROW_LABEL.match(ln)
                if m and canonical_section(m.group(1)) == "theme":
                    theme = re.split(r"\s{2,}", m.group(2).strip())[0][:30]
                    break

            seq = 0
            for ln in txt.splitlines():
                m = ROW_LABEL.match(ln)
                if not m:
                    continue
                label, body = m.group(1).strip(), m.group(2).strip()
                sec = canonical_section(label)
                if sec in ("other", "theme"):
                    continue
                for piece in SPLIT.split(body):
                    frag = BULLET.sub("", piece).strip()
                    if len(re.sub(r"\s", "", frag)) < 4 or len(frag) > 60:
                        continue
                    if not re.search(r"[가-힣]", frag):
                        continue
                    is_alt = bool(ALT_INLINE.search(frag)) or sec == "indoor_alternative"
                    setting = ("INDOOR_ALTERNATIVE" if is_alt
                               else SETTING_BY_SECTION.get(sec, "UNKNOWN"))
                    seq += 1
                    out.append(EvidenceRecord(
                        record_id=f"ev_{r['sha12']}_{info['page']}_{sec}_{seq:03d}",
                        source_type="INSTITUTION_SAMPLE",
                        source_path=r["path"], sha12=r["sha12"], page=info["page"],
                        institution_id=inst,
                        institution_type=r["establishment"],
                        year=None, month=month,
                        age_scope=ages, age_evidence_type=age_kind,
                        monthly_theme=theme,
                        source_section=sec, source_label=label,
                        week_position=None, week_label=None,
                        experience_text=(frag if sec == "week_experience" else None),
                        activity_text=(frag if sec != "week_experience" else None),
                        setting=setting, template_family=fam,
                        machine_readability=readable,
                        reuse_policy="CONTEXT_ONLY",
                    ))
    return out


def main() -> int:
    recs = build()
    OUT.write_text(json.dumps([dataclasses.asdict(r) for r in recs],
                              ensure_ascii=False), encoding="utf-8")
    line = "=" * 92
    print(line)
    print(" Evidence Store Prototype")
    print(line)
    print(f"  Evidence Record: {len(recs)}건  → {OUT.relative_to(ROOT)}")
    print(f"  기관: {len({r.institution_id for r in recs})}")
    print(f"  section: {dict(collections.Counter(r.source_section for r in recs).most_common())}")
    print(f"  setting: {dict(collections.Counter(r.setting for r in recs))}")
    print(f"  age_evidence_type: "
          f"{dict(collections.Counter(r.age_evidence_type for r in recs))}")
    print(f"  week_position 보유: "
          f"{sum(1 for r in recs if r.week_position is not None)}  "
          f"(원문에 주차가 명시된 줄만. 추정하지 않았다)")

    print("\n  outdoor_play record의 월 × 단일연령 분포")
    od = [r for r in recs if r.source_section == "outdoor_play"
          and r.setting == "OUTDOOR" and r.age_evidence_type == "SINGLE_AGE_PAGE"]
    print(f"  {'월':<5}{'만3세':>10}{'만4세':>10}{'만5세':>10}   (기관 수)")
    for m in range(1, 13):
        row = f"  {m:>2}월 "
        for age in (3, 4, 5):
            sub = [r for r in od if r.month == m and r.age_scope == (age,)]
            row += f"{len(sub):>6}({len({r.institution_id for r in sub})})"
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
