"""수집한 것 한 건. 아직 놀이가 아니라 원자료다 (ADR-015).

여기 담기는 것은 **사실뿐이다** — 제목·링크·날짜·채널. API 가 준 값을 그대로 옮긴다.
놀이 서술로 정리하는 것은 검열을 통과한 뒤의 일이고, 그때도 링크는 AI 에게 넘기지 않는다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

# 수집 결과가 쌓이는 곳. 주마다 파일 하나다.
# 검열을 통과한 것은 PR ② 가 별도 파일로 뽑는다 — 이 파일은 원자료다.
COLLECTED_DIR = Path(__file__).resolve().parents[3] / "resources" / "trends" / "collected"


@dataclass(frozen=True, slots=True)
class RawItem:
    source: str  # youtube · naver_news
    source_id: str  # videoId · 기사 원문 주소
    title: str
    description: str
    url: str
    published_at: str  # YYYY-MM-DD
    origin: str  # 채널 이름 · 언론사 도메인. 승인 목록과 대조하는 열쇠다
    facts: dict[str, Any] = field(default_factory=dict)  # 소스마다 다른 사실


def week_label(day: date) -> str:
    """2026-W39. ISO 주 번호다 — 월요일이 한 주의 시작이라 월요일 수집과 맞는다."""
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def save(items: list[RawItem], day: date, directory: Path | None = None) -> Path:
    """그 주 파일에 덮어쓴다.

    같은 주에 두 번 돌리면 뒤엣것만 남는다. 초기 시드처럼 여러 번 돌릴 때
    앞 결과가 섞이면 무엇이 언제 들어온 것인지 못 가린다.
    """
    directory = directory or COLLECTED_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{week_label(day)}.json"
    body = {
        "collected_on": day.isoformat(),
        "count": len(items),
        "items": [asdict(item) for item in items],
    }
    # ensure_ascii=False — 한글이 \uXXXX 로 박히면 PR diff 를 사람이 못 읽는다.
    # 사람이 읽고 이상한 줄을 지우는 것이 승인 절차다 (ADR-015).
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load(path: Path) -> list[RawItem]:
    body = json.loads(path.read_text(encoding="utf-8"))
    return [RawItem(**item) for item in body["items"]]
