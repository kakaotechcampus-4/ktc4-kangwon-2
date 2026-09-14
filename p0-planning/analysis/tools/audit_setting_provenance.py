"""§3. Activity setting provenance 전수 감사 (분석 전용).

v0.2.1 Draft의 각 Activity evidence를 원문 PDF의 **셀**로 되돌려, 그 Activity가
실제로 어느 section에서 관찰되었는지 판정한다.

판정 신호는 두 가지이며 **둘 다 원문에 적힌 글자**다.

    1. 행 label      표의 첫 열 — 바깥놀이 / 실외놀이 / 실내놀이 / 대체활동 …
    2. 인라인 태그   셀 안 `<바깥놀이>` `<실내놀이>` `[실내대체활동]` …

인라인 태그가 있으면 그것이 행 label보다 구체적이므로 우선한다. 예: 큰빛 9월은
`흥미 예상 놀이` 행 안에서 `<실내놀이> … <바깥놀이> …`로 다시 나뉜다.

추측하지 않는다. 원문에서 label을 못 찾으면 `SETTING_NOT_RECOVERABLE`이다.

    python analysis/tools/audit_setting_provenance.py
"""

from __future__ import annotations

import collections
import io
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "tools"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from cell_extract import _rules, extract_cells  # noqa: E402

DRAFT = ROOT / "data" / "activities" / "activity_reference_v0_2_1_draft.json"

# ---- 원문 section 어휘. 표기 흔들림을 모두 적는다.
OUTDOOR_WORDS = ("바깥놀이", "바깥 놀이", "실외놀이", "실외 놀이", "실외", "야외놀이",
                 "바깥", "실외활동", "산책")
INDOOR_WORDS = ("실내놀이", "실내 놀이", "실내활동", "실내대체활동", "실내대체",
                "실내 대체", "실내")
AMBIGUOUS_WORDS = ("실내외", "실내·외", "실내 외", "내외")
"""`실내외 놀이`는 실내와 실외를 **함께** 가리키는 행이다.

`실내`가 들어 있다는 이유로 NON_OUTDOOR로 보면 안 되고, `실외`도 문자열로는 없다.
어느 쪽 근거도 되지 못하므로 판정하지 않는다.
"""

ALT_WORDS = ("대체활동", "대체놀이", "대체")
"""`대체`는 그 자체로 실내를 뜻하지 않는다.

표에서 `바깥놀이 / [대체활동]`은 **두 줄짜리 병합 행 label**이다. 윗줄이 바깥놀이
행이고 아랫줄이 그 대체 항목 줄이다. 따라서 행 label에 `대체`가 섞였다는 이유만으로
NON_OUTDOOR로 보면 바깥놀이 행 전체가 뒤집힌다.

대체 여부는 **항목 자신이 대체 표시로 시작하는가**로만 판정한다.
"""

TAG = re.compile(r"[<\[【]([^>\]】]{1,14})[>\]】]")
LEADING_ALT = re.compile(r"^\s*[\[【(]\s*(실내\s*)?대체")
"""항목이 `[대체]` `[실내대체활동]` `【대체활동 :` 로 시작하면 그 항목이 대체안이다.

반면 `- 꼭꼭 숨어라 (대체활동-꼭꼭 숨어라)`처럼 **뒤에 붙는** 괄호는 "이 바깥놀이의
대체안은 X"라는 뜻이므로 본 항목의 setting을 뒤집지 않는다.
"""


def nrm(s: str) -> str:
    return re.sub(r"[\s.,·…~!?\"'()\[\]<>【】♥•◆▶⦁\-/]+", "", s or "")


def classify_word(text: str) -> str | None:
    """단일 태그/라벨 어휘 판정. 실내가 더 구체적이므로 먼저 본다."""
    t = nrm(text)
    if any(nrm(w) in t for w in AMBIGUOUS_WORDS):
        return None
    for w in INDOOR_WORDS:
        if nrm(w) in t:
            return "NON_OUTDOOR"
    for w in OUTDOOR_WORDS:
        if nrm(w) in t:
            return "OUTDOOR"
    return None


def classify_row_label(text: str) -> str | None:
    """행 label 판정.

    바깥놀이와 대체가 함께 있으면 **바깥놀이 행**이다(병합 행 label).
    실내 어휘가 단독으로 있을 때만 NON_OUTDOOR다.
    """
    t = nrm(text)
    if any(nrm(w) in t for w in AMBIGUOUS_WORDS) and not any(
        nrm(w) in t for w in ("바깥놀이", "바깥", "산책")
    ):
        return None
    has_out = any(nrm(w) in t for w in OUTDOOR_WORDS)
    has_in = any(nrm(w) in t for w in INDOOR_WORDS)
    if has_out:
        return "OUTDOOR"
    if has_in:
        return "NON_OUTDOOR"
    return None


HANGUL = re.compile(r"[가-힣]")
PREFIX_LABEL = re.compile(
    r"^[♥•◆▶⦁*\-–—\s]*"
    r"(바깥\s*놀이|실외\s*놀이|실내\s*놀이|실외\s*활동|실내\s*활동|실외|실내)"
    r"\s*[-–—:·]?"
)
"""괄호 없이 **항목 맨 앞에 붙는** section 표기.

공립아이사랑 월간계획안은 `♥바깥놀이-비석치기`처럼 태그를 괄호 없이 붙인다.
이 표기는 원문 글자이므로 태그와 같은 근거로 취급한다.
"""
ALT_TAG = re.compile(r"[\[【(]\s*(?:실내\s*)?대체[^\]】)]*[\]】)]")
BARE_ALT_TAG = re.compile(r"^[\[【(]\s*(?:실내\s*)?대체\s*(?:활동|놀이)?\s*[\]】)]$")
"""대체 표기는 두 종류이고 **지배 범위가 반대**다.

    A 구분자형   `가을 하늘 보며 산책하기 [실내대체] 스카프로 가을바람 표현하기`
                 괄호 안에 태그 말고는 아무것도 없다. **괄호 뒤**가 대체안이다.

    B 내용포함형 `⦁무궁화 꽃이 피었습니다. 【대체활동 : 강강술래를 해요】 ⦁다음 항목`
                 괄호 안에 대체안이 들어 있다. **괄호 안**만 대체안이고 뒤는 다음 본 항목이다.

둘을 구분하지 않으면 A에서는 대체안이 바깥놀이로, B에서는 다음 본 항목이
대체안으로 뒤집힌다.
"""


def needle_pattern(needle: str) -> re.Pattern | None:
    """글자 사이 공백/구두점을 허용하되 **낱말 경계**를 요구하는 패턴.

    `팽이 놀이`가 `실팽이 놀이` 안에서 매칭되면 안 된다. 앞 글자가 한글이면
    더 긴 낱말의 일부이므로 제외한다.
    """
    chars = [c for c in needle if not re.match(r"[\s.,·…~!?\"'()\[\]<>【】♥•◆▶⦁\-/]", c)]
    if len(chars) < 2:
        return None
    sep = r"[\s.,·…\-]*"
    body = sep.join(re.escape(c) for c in chars)
    # 양쪽 모두 낱말 경계를 요구한다. 왼쪽만 막으면 `겨울 음식`이
    # `겨울 음식에는 무엇이 있을까?` 안에서 잡힌다.
    return re.compile(r"(?<![가-힣])" + body + r"(?![가-힣])")


def occurrences_in_cell(cell_items: list[str], row_label: str, needle: str):
    """셀 안 needle의 **모든** 출현을 판정해 돌려준다."""
    pat = needle_pattern(needle)
    if pat is None:
        return []
    found = []
    for item in cell_items:
        for m in pat.finditer(item):
            prefix = item[: m.end()]
            # ① 항목 자신이 대체 표시로 시작하면 그 항목이 대체안이다
            if LEADING_ALT.match(item):
                found.append(("NON_OUTDOOR", "leading-alt", item))
                continue
            # ② 대체 표기가 있는 줄.
            #    `⦁A 【대체활동 : X】 ⦁B 【대체활동 : Y】`처럼 한 줄에 대체 표기가
            #    여러 개 오므로 "앞/뒤"로 가르면 B가 X의 뒤라는 이유로 뒤집힌다.
            #    실제 의미는 **괄호 안에 들어 있는가**다. 안이면 대체안, 밖이면
            #    그 줄의 본 항목(바깥놀이)이다.
            spans = [(x.start(), x.end(), bool(BARE_ALT_TAG.match(x.group(0))))
                     for x in ALT_TAG.finditer(item)]
            if spans:
                if any(s0 <= m.start() < s1 for s0, s1, bare in spans if not bare):
                    found.append(("NON_OUTDOOR", "inside-alt-bracket", item))
                elif any(s1 <= m.start() for _, s1, bare in spans if bare):
                    found.append(("NON_OUTDOOR", "after-alt-separator", item))
                else:
                    found.append(("OUTDOOR", "outside-alt-bracket", item))
                continue
            # ②b 괄호 없는 접두 표기 `♥바깥놀이-비석치기`
            pm = PREFIX_LABEL.match(item)
            if pm and m.start() < pm.end():
                got = classify_word(pm.group(1))
                if got:
                    found.append((got, f"prefix<{pm.group(1)}>", item))
                    continue
            # ③ needle 앞에 나온 마지막 인라인 section 태그
            got = None
            for tag in reversed(TAG.findall(prefix)):
                got = classify_word(tag)
                if got:
                    found.append((got, f"inline<{tag}>", item))
                    break
            if got:
                continue
            # ③ 행 label
            got = classify_row_label(row_label)
            found.append((got, f"row[{row_label.strip()[:40]}]", item))
    return found


# ------------------------------------------------- 태그 열 레이아웃 복원

TAG_ONLY = re.compile(
    r"^[-–—♥•◆▶⦁*\s]*[\[【(]\s*(바깥|실외|실내\s*대체|대체|실내)\s*[\]】)]$"
)
"""`[바깥]` `[대체]` `[실내대체]` `-[실내대체]`처럼 **태그 하나뿐인 낱말**.

앞의 글머리 기호(`-` `♥` `⦁`)는 원문에서 태그에 붙어 한 낱말로 추출되므로 허용한다.
"""


def tagband_cells(page) -> dict[tuple[float, float, int], list[str]]:
    """`[바깥] / [대체]` 태그가 별도 열에 있는 표를 복원한다.

    예일어린이집 월간계획안은 한 셀이 이렇게 생겼다.

        겨울 풍경
        [바깥]  찾기          ← 태그가 **두 줄에 걸친 label의 가운데**에 찍힌다
        장갑 짝
        [대체]  찾기

    줄 단위로 읽으면 태그가 wrap된 label 사이에 끼어들어 `겨울 풍경 [바깥] 찾기`가
    되고 label을 찾을 수 없다. 태그는 세로 위치로 자기 항목을 가리키므로,
    **각 글자줄을 y가 가장 가까운 태그에 배정**하면 원문 항목이 복원된다.

    태그가 없는 셀은 돌려주지 않는다. 추측하지 않는다.
    """
    vs, hs = _rules(page)
    if not vs or not hs:
        return {}
    row_edges = sorted({y for y, _, _ in hs})
    words = page.get_text("words")
    out: dict[tuple[float, float, int], list[str]] = {}

    for top, bottom in zip(row_edges, row_edges[1:]):
        if bottom - top < 6:
            continue
        band = [w for w in words if top < (w[1] + w[3]) / 2 < bottom]
        if not band:
            continue
        cols = sorted({x for x, y0, y1 in vs if y0 <= top + 2 and y1 >= bottom - 2})
        if len(cols) < 2:
            continue

        def col_of(x: float) -> int:
            for i in range(len(cols) - 1):
                if cols[i] <= x < cols[i + 1]:
                    return i
            return len(cols) - 2

        by_col: dict[int, list] = collections.defaultdict(list)
        for w in band:
            by_col[col_of(w[0])].append(w)

        for col, ws in by_col.items():
            cand_tags = [w for w in ws if TAG_ONLY.match(w[4])]
            rest = [w for w in ws if not TAG_ONLY.match(w[4])]
            if not cand_tags or not rest:
                continue

            def _ym(w):
                return (w[1] + w[3]) / 2

            # 태그가 **셀 왼쪽 끝의 별도 열**에 있을 때만 태그 열 레이아웃이다.
            # 같은 줄 왼쪽에 한글이 있으면 그것은 `A [실내대체] B`처럼 한 줄 안의
            # 구분자이지 열이 아니다. 구분하지 않으면 구분자 앞의 바깥놀이 항목이
            # 통째로 대체안으로 넘어간다.
            tags = [
                t for t in cand_tags
                if not any(
                    HANGUL.search(w[4]) and w[0] < t[0] and abs(_ym(w) - _ym(t)) < 0.6
                    for w in rest
                )
            ]
            if not tags:
                continue
            lines: dict[float, list] = collections.defaultdict(list)
            for w in rest:
                lines[round((w[1] + w[3]) / 2, 1)].append(w)

            def ymid(w):
                return round((w[1] + w[3]) / 2, 1)

            # 태그가 **자기 줄에 혼자** 있으면 두 줄짜리 label의 가운데에 찍힌
            # 것이므로 위쪽 줄도 지배한다. 글자와 같은 줄에 있으면 그 줄부터
            # 아래로만 지배한다. 이 구분이 없으면 괴산하나처럼 태그가 항목의
            # 첫 줄에 오는 표에서 **바로 위의 바깥놀이 항목이 대체안으로 뒤집힌다.**
            centered = [not any(abs(ymid(w) - ymid(t)) < 0.6 for w in rest)
                        for t in tags]
            buckets: dict[int, list[tuple[float, str]]] = collections.defaultdict(list)
            line_min_x: dict[float, float] = {}
            for y, lws in lines.items():
                line_min_x[y] = min(w[0] for w in lws)
                cand = [k for k in range(len(tags))
                        if centered[k] or ymid(tags[k]) <= y + 1]
                i = (min(cand, key=lambda k: abs(ymid(tags[k]) - y))
                     if cand else -1)
                buckets[i].append(
                    (y, " ".join(w[4] for w in sorted(lws, key=lambda w: w[0])))
                )

            # 첫 태그 위에 남은 줄은 **그 태그 항목의 첫 줄일 수도 있고**(예일
            #   `전통` / `[바깥] 음식을 배달해요`), 태그와 무관한 **별개 본 항목**일
            #   수도 있다(괴산 `- 분필로내이름끼적이기` / `-[실내대체] 몸으로 …`).
            # 들여쓰기·좌표로 두 경우를 안정적으로 가르지 못했다. 잘못 붙이면
            # 바깥놀이 항목이 대체안으로 뒤집히므로 **붙이지 않고 태그 없이 남긴다.**
            # 그 줄들은 판정되지 않고 SETTING_NOT_RECOVERABLE로 남는다 — 추측하지
            # 않는 쪽을 택한다.
            items = []
            order = sorted(buckets, key=lambda k: -1e9 if k < 0 else ymid(tags[k]))
            for i in order:
                body = " ".join(t for _, t in sorted(buckets[i]))
                items.append(body if i < 0 else f"{tags[i][4]} {body}")
            if items:
                out[(top, bottom, col)] = items
    return out


def main() -> int:
    import pymupdf

    cat = json.loads(DRAFT.read_text("utf-8"))
    origins = {o["origin_id"]: o for o in cat["origins"]}

    # PDF별 · 모드별 셀 캐시
    cache: dict[str, dict[tuple[float, float], dict[int, list[str]]]] = {}

    def cells_for(path: str, page: int, rejoin: bool | None):
        """rejoin=None이면 태그 열 레이아웃 복원 모드."""
        key = f"{path}#{page}#{rejoin}"
        if key in cache:
            return cache[key]
        rows: dict[tuple[float, float], dict[int, list[str]]] = {}
        p = ROOT / path
        if p.exists():
            try:
                doc = pymupdf.open(str(p))
                if 0 <= page - 1 < doc.page_count:
                    got = (tagband_cells(doc[page - 1]) if rejoin is None
                           else extract_cells(doc[page - 1], rejoin=rejoin))
                    for (top, bot, col), items in got.items():
                        rows.setdefault((top, bot), {})[col] = items
                doc.close()
            except Exception:
                pass
        cache[key] = rows
        return rows

    ALT_SIGNALS = {"leading-alt", "inside-alt-bracket", "outside-alt-bracket",
                   "after-alt-separator"}

    def hits_for(path: str, page: int, needle: str, rejoin: bool | None):
        """한 PDF page에서 needle의 모든 출현 판정."""
        out = []
        rows = cells_for(path, page, rejoin)
        for _, cols in rows.items():
            if not cols:
                continue
            order = sorted(cols)
            for col in order:
                # tagband 모드의 dict에는 태그가 있는 셀만 들어 있으므로 첫 열이
                # label 열이 아니다. 건너뛰면 첫 열 항목을 통째로 놓친다.
                if rejoin is not None and col == order[0]:
                    continue  # 첫 열은 행 label 열이다
                # 같은 행에서 **왼쪽에 있는 모든 셀**이 그 셀의 label context다.
                # 세로쓰기 병합 label(`바 / 깥 / 놀 / 이` + `실외놀이`)이 두 열로
                # 쪼개져 있어 첫 열만 보면 `이`만 잡힌다.
                row_label = " ".join(
                    " ".join(cols[c]) for c in order if c < col
                )
                out.append(occurrences_in_cell(cols[col], row_label, needle))
        return [h for group in out for h in group]

    def verdict_of(hits):
        kinds = {h[0] for h in hits if h[0]}
        if kinds == {"OUTDOOR"}:
            return "OUTDOOR"
        if kinds == {"NON_OUTDOOR"}:
            return "NON_OUTDOOR"
        if kinds == {"OUTDOOR", "NON_OUTDOOR"}:
            return "BOTH_IN_SOURCE"
        return None

    results = []
    for a in cat["activities"]:
        ev_verdicts = []
        for e in a.get("evidence", []):
            origin = origins.get(e["origin_id"], {})
            path = origin.get("path", "")
            page = e.get("page", 1)
            needle = e.get("observed_label") or a["label"]
            # 두 읽기 모드를 모두 돌린다.
            #   rejoin=False  `<바깥놀이 항목> [실내대체활동] <대체안>` 한 줄 레이아웃
            #                 을 정확히 읽는다. 대신 셀 안 줄바꿈된 label은 못 찾는다.
            #   rejoin=True   줄바꿈된 label을 복원한다. 대신 위 한 줄 레이아웃 두 개가
            #                 붙어 section 판정이 섞인다.
            # 대체 태그 신호가 잡힌 쪽이 그 줄에 대해 더 구체적이므로 우선한다.
            #   rejoin=None   `[바깥] / [대체]` 태그 열 레이아웃 복원. 가장 구체적이다.
            tag_hits = hits_for(path, page, needle, rejoin=None)
            raw_hits = hits_for(path, page, needle, rejoin=False)
            join_hits = hits_for(path, page, needle, rejoin=True)
            if verdict_of(tag_hits):
                hits, mode = tag_hits, "tagband"
            elif any(h[1] in ALT_SIGNALS for h in raw_hits):
                hits, mode = raw_hits, "raw"
            elif verdict_of(raw_hits):
                hits, mode = raw_hits, "raw"
            elif verdict_of(join_hits):
                hits, mode = join_hits, "rejoin"
            else:
                hits, mode = (raw_hits or join_hits), "raw" if raw_hits else "rejoin"
            verdict = verdict_of(hits)
            pick = next((h for h in hits if h[0] == verdict), hits[0] if hits else None)
            signal = pick[1] if pick else None
            quote = pick[2] if pick else None
            ev_verdicts.append({
                "origin_id": e["origin_id"],
                "page": page,
                "observed_label": needle,
                "observed_section": e.get("observed_section"),
                "observed_source_label": e.get("observed_source_label"),
                "verdict": verdict or "SETTING_NOT_RECOVERABLE",
                "signal": signal,
                "read_mode": mode,
                "quote": (quote or "")[:120],
                "source": path,
            })

        kinds = {v["verdict"] for v in ev_verdicts}
        if "BOTH_IN_SOURCE" in kinds:
            kinds = (kinds - {"BOTH_IN_SOURCE"}) | {"OUTDOOR", "NON_OUTDOOR"}
        if kinds == {"OUTDOOR"}:
            overall = "SOURCE_CONFIRMED_OUTDOOR"
        elif kinds == {"NON_OUTDOOR"}:
            overall = "SOURCE_CONFIRMED_NON_OUTDOOR"
        elif "OUTDOOR" in kinds and "NON_OUTDOOR" in kinds:
            overall = "MIXED_SETTING_EVIDENCE"
        elif "OUTDOOR" in kinds:
            overall = "SOURCE_CONFIRMED_OUTDOOR"     # 나머지는 미복원
        elif "NON_OUTDOOR" in kinds:
            overall = "SOURCE_CONFIRMED_NON_OUTDOOR"
        else:
            overall = "SETTING_NOT_RECOVERABLE"

        results.append({
            "activity_id": a["activity_id"],
            "label": a["label"],
            "setting": a["setting"],
            "months": a.get("applicable_months"),
            "overall": overall,
            "evidence": ev_verdicts,
        })

    out = ROOT / "analysis" / "tmp" / "setting_audit.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    print("=" * 78)
    print(f" Setting Provenance 전수 감사 — {len(results)} activities")
    print("=" * 78)
    c = collections.Counter(r["overall"] for r in results)
    for k in ("SOURCE_CONFIRMED_OUTDOOR", "MIXED_SETTING_EVIDENCE",
              "SOURCE_CONFIRMED_NON_OUTDOOR", "SETTING_NOT_RECOVERABLE"):
        print(f"  {k:<32}{c.get(k, 0):>4}")
    print()

    for kind in ("SOURCE_CONFIRMED_NON_OUTDOOR", "MIXED_SETTING_EVIDENCE"):
        rows = [r for r in results if r["overall"] == kind]
        if not rows:
            continue
        print("-" * 78)
        print(f" [{kind}] {len(rows)}건")
        for r in rows:
            print(f"\n   {r['label']}  (setting={r['setting']}, months={r['months']})")
            for v in r["evidence"]:
                print(f"     {v['verdict']:<26} {v['signal']}")
                print(f"       obs={v['observed_label']!r}")
                print(f"       원문: {v['quote']}")
                print(f"       src : {pathlib.Path(v['source']).name}")
    print(f"\n  저장: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
