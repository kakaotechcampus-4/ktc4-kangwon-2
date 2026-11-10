"""서버에 있는 경로가 docs/api-spec.md 에 적혀 있는지 본다.

**한쪽만 본다.** 서버에 있는데 문서에 없으면 실패한다. 문서에만 있는 것(아직 안 만든 제안)은 둔다.
**같은 줄에 「메서드 경로」가 있으면 적힌 것으로 친다** — 산문 · 부정문(「…는 없다」) 속
언급도 센다.
"""

import re
from pathlib import Path

from app.main import app

SPEC = Path(__file__).resolve().parents[2] / "docs" / "api-spec.md"
METHODS = "GET|POST|PUT|PATCH|DELETE"
# `GET·PUT /api/x` · `GET · PUT /api/x` · 코드 블록의 `POST   /api/x`. 쿼리와 끝 구두점은 뗀다.
# 메서드와 경로는 같은 줄이어야 한다 — `\s` 는 줄을 넘어 표 아랫줄 경로를 잘못 센다.
MENTION = re.compile(
    rf"(?<![A-Za-z])((?:{METHODS})(?:[ \t]*[·/,][ \t]*(?:{METHODS}))*)"
    r"[ \t]+(/(?:api|health)[^\s`]*)"
)


def _normalize(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path)


def _spec_ops() -> set[tuple[str, str]]:
    ops = set()
    for methods, path in MENTION.findall(SPEC.read_text(encoding="utf-8")):
        path = _normalize(path.split("?")[0].rstrip(".,;:)·*|"))
        ops |= {(m, path) for m in re.findall(METHODS, methods)}
    return ops


def test_every_server_route_is_in_api_spec():
    server = {
        (method.upper(), _normalize(path)): path
        for path, item in app.openapi()["paths"].items()
        for method in item
        if method.upper() in METHODS.split("|")
    }
    missing = sorted(set(server) - _spec_ops())
    assert not missing, "docs/api-spec.md 에 없는 경로 — 계약을 먼저 적는다:\n" + "\n".join(
        f"  {method:6} {server[method, path]}" for method, path in missing
    )
