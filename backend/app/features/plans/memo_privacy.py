"""계획안 생성 「요청 사항」의 아동 이름을 LLM 으로 나가기 직전에 가명으로 바꾼다.

api-spec §9 · ADR-060.

메모 원문만 바꾼다. 요청 전체를 바꾸면 누리과정 문장 속 「하나씩」 같은 말까지 이름으로
보고 바꾼다. 답은 통째로 되돌린다 — 반영 못한 요청 요약에도 가명이 섞일 수 있다.
Core 는 원문 메모를 보고 검증하므로, Core 에 돌아가는 답도 실명이어야 맞는다.
"""

from __future__ import annotations

import json
from dataclasses import replace

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.centers.models import Child, Class
from app.shared.childCode import (
    NameTable,
    SubstitutionError,
    load_pool,
    mask,
    table_for_text,
    unmask,
)

MASK_FAILED = HTTPException(
    status.HTTP_422_UNPROCESSABLE_ENTITY,
    detail={
        "code": "VALUE_INVALID",
        "message": (
            "요청 사항의 아이 이름을 가명으로 바꾸지 못해 AI 를 부르지 않았어요. "
            "이름을 빼고 다시 적어 주세요."
        ),
        "fields": ["memo"],
    },
)


def center_name_table(session: Session, class_id: int, text: str) -> NameTable | None:
    """그 반이 속한 원의 아이 전부(다른 반 포함)를 보고, 글에 나온 아이로 표를 만든다.

    교사는 옆 반 아이 이름도 적을 수 있다(멘토 리뷰 #380). 원 하나는 300명을 넘지 않는다.
    바꾸지 못하면 SubstitutionError — 부르는 쪽이 LLM 을 부르지 않고 에러로 바꾼다.
    """
    if not text:
        return None
    center_id = select(Class.center_id).where(Class.id == class_id).scalar_subquery()
    rows = session.execute(
        select(Child.class_id, Child.name, Child.code)
        .join(Class, Class.id == Child.class_id)
        .where(Class.center_id == center_id)
        .order_by(Child.id)
    ).all()
    own = [(name, code) for owner, name, code in rows if owner == class_id]
    others = [(name, code) for owner, name, code in rows if owner != class_id]
    return table_for_text(load_pool(), own, others, text)


def memo_name_table(session: Session, class_id: int, memo: str) -> NameTable | None:
    """메모에 원 아이 이름이 있을 때만 표를 만든다. 바꾸지 못하면 LLM 을 부르기 전에 422."""
    try:
        return center_name_table(session, class_id, memo)
    except SubstitutionError as error:
        raise MASK_FAILED from error


def mask_memo(memo: str, table: NameTable | None) -> str:
    return memo if table is None else mask(memo, table)


def unmask_text(text: str, table: NameTable | None) -> str:
    return text if table is None else unmask(text, table)


class MemoMaskFailed(Exception):
    """보낼 요청에 메모 속 아이 이름이 남았다. Core 가 provider 오류를 감싸므로 라우터가 꺼낸다."""


def raise_if_mask_failed(error: BaseException) -> None:
    """Core 가 감싼 원인 사슬에 MemoMaskFailed 가 있으면 422 로 바꾼다."""
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, MemoMaskFailed):
            raise MASK_FAILED from error
        current = current.__cause__ or current.__context__


class MaskedMemoProvider:
    """어떤 생성 공급자든 감싼다: 요청의 user_content 속 메모만 가명으로, 답은 실명으로.

    수리 요청은 앞 답(실명으로 되돌린 것)을 다시 싣는다. 메모에 나온 아이 이름이 요청 어디에든
    남아 있으면 부르지 않는다 — 「하나씩」처럼 낱말과 겹쳐도 내보내지 않는 쪽을 고른다.
    """

    def __init__(self, inner, memo: str, table: NameTable) -> None:
        self._inner = inner
        self._table = table
        # 요청 본문은 JSON 이다. 메모가 들어간 모양(따옴표 안)을 그대로 찾아 바꾼다.
        self._real = json.dumps(memo, ensure_ascii=False)[1:-1]
        self._fake = json.dumps(mask(memo, table), ensure_ascii=False)[1:-1]
        self._names = tuple(variant for variant in table.masking if variant in memo)

    def __getattr__(self, name):
        method = getattr(self._inner, name)
        if not callable(method):
            return method

        def call(request, *args, **kwargs):
            masked = replace(
                request, user_content=request.user_content.replace(self._real, self._fake)
            )
            text = masked.user_content + masked.system_prompt
            if any(variant in text for variant in self._names):
                raise MemoMaskFailed
            response = method(masked, *args, **kwargs)
            return replace(response, content=unmask(response.content, self._table))

        return call


def with_masked_memo(provider, memo: str, table: NameTable | None):
    return provider if table is None else MaskedMemoProvider(provider, memo, table)
