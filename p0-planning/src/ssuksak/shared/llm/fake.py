"""Fake LLM Adapter.

CLAUDE.md §16·§25: 첫 Slice에서는 Fake LLM으로 Rule과 Validation을 먼저 검증하고,
실제 Adapter는 Core 규칙과 Golden Test가 안정된 뒤 연결한다.

여러 mode를 제공하는 이유는 theme_id 교체 방어와 스키마 검증을 실제로
테스트해야 하기 때문이다.
"""

from __future__ import annotations

from enum import Enum

from .port import LLMUnavailableError, ThemePolishRequest, ThemePolishResponse


class FakeLLMMode(str, Enum):
    ECHO_LABEL = "ECHO_LABEL"
    """Reference label을 그대로 반환한다."""

    POLISH = "POLISH"
    """의미를 유지한 자연스러운 문장을 만든다(기본)."""

    WRONG_THEME_ID = "WRONG_THEME_ID"
    """다른 theme_id를 반환한다 — 방어 2·4 테스트용."""

    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
    """스키마를 위반한 출력을 반환한다."""

    BLANK_VALUE = "BLANK_VALUE"
    """공백 표현을 반환한다."""

    UNAVAILABLE = "UNAVAILABLE"
    """재시도 후 실패를 시뮬레이션한다."""


class FakeLLM:
    """공급자 없이 동작하는 결정론적 LLM.

    docs/demo-source-of-truth.md §31 / CLAUDE.md §20:
    문장 전체를 exact match하지 않으므로 표현이 결정론적이면 충분하다.
    """

    def __init__(
        self,
        mode: FakeLLMMode = FakeLLMMode.POLISH,
        *,
        monthly_proposal: object | None = None,
    ) -> None:
        """Args:
        monthly_proposal: `plan_monthly()`가 돌려줄 `MonthlyPlanProposal`.

            **Fake는 Planner algorithm을 흉내 내지 않는다.** 한 달 흐름을
            구성하는 것은 이 Fake가 할 수 있는 일이 아니고, 흉내 낸 결과를
            테스트가 검증하면 실제 계약이 아니라 Fake를 검증하게 된다.
            테스트가 명시적으로 설정한 Proposal만 돌려준다.
        """
        self.mode = mode
        self.calls: list[ThemePolishRequest] = []
        self.batch_calls: list[object] = []
        self.monthly_calls: list[object] = []
        self._monthly_proposal = monthly_proposal
        self.cell_calls: list[object] = []
        self._cell_proposal: object | None = None

    @property
    def call_count(self) -> int:
        """다듬은 **항목** 수. Batch 1회에 12항목이면 12."""
        return len(self.calls)

    @property
    def request_count(self) -> int:
        """실제 **요청** 수. Batch 1회에 12항목이면 1."""
        batched_items = sum(len(getattr(b, "items", ())) for b in self.batch_calls)
        single_calls = len(self.calls) - batched_items
        return len(self.batch_calls) + single_calls

    @property
    def batch_call_count(self) -> int:
        return len(self.batch_calls)

    @property
    def was_called(self) -> bool:
        return bool(self.calls) or bool(self.batch_calls)

    def polish_theme(self, request: ThemePolishRequest) -> ThemePolishResponse:
        self.calls.append(request)

        if self.mode is FakeLLMMode.UNAVAILABLE:
            raise LLMUnavailableError("FakeLLM: 재시도 후 최종 실패")

        if self.mode is FakeLLMMode.SCHEMA_VIOLATION:
            # 스키마 검증을 통과하지 못하는 형태를 의도적으로 만든다.
            raise ValueError("FakeLLM: Structured Output 스키마 위반 (value 누락)")

        if self.mode is FakeLLMMode.WRONG_THEME_ID:
            return ThemePolishResponse(
                theme_id=f"{request.selected_theme_id}__llm_swapped",
                value=f"{request.selected_theme_label} (교체 시도)",
            )

        if self.mode is FakeLLMMode.BLANK_VALUE:
            return ThemePolishResponse(theme_id=request.selected_theme_id, value="   ")

        if self.mode is FakeLLMMode.ECHO_LABEL:
            return ThemePolishResponse(
                theme_id=request.selected_theme_id, value=request.selected_theme_label
            )

        value = f"{request.selected_theme_label}을 함께 살펴보아요."
        if request.constraints.max_chars is not None:
            value = value[: request.constraints.max_chars]

        return ThemePolishResponse(theme_id=request.selected_theme_id, value=value)

    # ------------------------------------------------------------- Batch

    def polish_themes(self, request):
        """Batch 경로. mode 의미를 단건과 동일하게 유지한다.

        내부에서 단건 로직을 재사용하므로 WRONG_THEME_ID / BLANK_VALUE /
        UNAVAILABLE 등 기존 mode가 Batch에서도 같은 의미로 동작한다.
        `batch_calls`는 실제 요청 횟수(1회)를 세고, `calls`는 항목 수를 센다.
        """
        from .batch import PolishedThemeOut, ThemeBatchPolishResponse

        self.batch_calls.append(request)

        if self.mode is FakeLLMMode.SCHEMA_VIOLATION:
            raise ValueError("FakeLLM: Batch Structured Output 스키마 위반")

        items = []
        for item in request.items:
            single = ThemePolishRequest(
                task="polish_yearly_theme_label",
                selected_theme_id=item.theme_id,
                selected_theme_label=item.label,
                period_key=item.period_key,
                ages=request.ages,
                event_labels=item.event_labels,
                constraints=request.constraints,
            )
            polished = self.polish_theme(single)
            out = PolishedThemeOut.model_construct(
                period_key=item.period_key,
                theme_id=polished.theme_id,
                value=polished.value,
            ) if self.mode is FakeLLMMode.BLANK_VALUE else PolishedThemeOut(
                period_key=item.period_key,
                theme_id=polished.theme_id,
                value=polished.value,
            )
            items.append(out)

        # BLANK_VALUE mode는 스키마 검증을 우회해 공백 값을 실제로 전달한다.
        # 규약을 어기는 Provider를 재현해 reconcile의 blank 검사를 실제로 태운다.
        if self.mode is FakeLLMMode.BLANK_VALUE:
            return ThemeBatchPolishResponse.model_construct(themes=items)
        return ThemeBatchPolishResponse(themes=items)

    # ------------------------------------------------------- Monthly Planner

    @property
    def monthly_call_count(self) -> int:
        return len(self.monthly_calls)

    def set_monthly_proposal(self, proposal: object) -> None:
        """테스트가 반환값을 명시적으로 정한다."""
        self._monthly_proposal = proposal

    def plan_monthly(self, request):
        """설정된 Proposal을 돌려준다. **Planner를 흉내 내지 않는다.**

        반환 전에 실제 Adapter와 **같은 reconcile**을 태운다. 그래야 Fake를
        쓰는 소비자 테스트가 실제 계약과 같은 경계를 본다.
        """
        from .monthly import reconcile_monthly_proposal

        self.monthly_calls.append(request)

        if self.mode is FakeLLMMode.UNAVAILABLE:
            raise LLMUnavailableError("FakeLLM: 재시도 후 최종 실패")
        if self.mode is FakeLLMMode.SCHEMA_VIOLATION:
            raise ValueError("FakeLLM: Monthly Structured Output 스키마 위반")

        if self._monthly_proposal is None:
            raise ValueError(
                "FakeLLM.plan_monthly에 반환할 Proposal이 설정되지 않았다. "
                "monthly_proposal=... 또는 set_monthly_proposal()로 지정하라."
            )

        return reconcile_monthly_proposal(
            self._monthly_proposal,
            expected_theme_id=request.expected_theme_id,
            expected_week_ids=request.expected_week_ids,
            reference_labels=request.reference_labels,
            valid_grounding_refs=request.valid_grounding_refs,
        )

    # --------------------------------------------------- Cell Regeneration

    @property
    def cell_call_count(self) -> int:
        return len(self.cell_calls)

    def set_cell_proposal(self, proposal: object) -> None:
        """테스트가 반환값을 명시적으로 정한다."""
        self._cell_proposal = proposal

    def regenerate_monthly_cell(self, request):
        """설정된 Cell 제안을 돌려준다. **Planner를 흉내 내지 않는다.**

        반환 전에 실제 Adapter와 같은 reconcile을 태운다.
        """
        from .monthly_cell import reconcile_cell_proposal

        self.cell_calls.append(request)

        if self.mode is FakeLLMMode.UNAVAILABLE:
            raise LLMUnavailableError("FakeLLM: 재시도 후 최종 실패")
        if self.mode is FakeLLMMode.SCHEMA_VIOLATION:
            raise ValueError("FakeLLM: Cell Structured Output 스키마 위반")

        if self._cell_proposal is None:
            raise ValueError(
                "FakeLLM.regenerate_monthly_cell에 반환할 제안이 설정되지 않았다. "
                "set_cell_proposal()로 지정하라."
            )

        return reconcile_cell_proposal(
            self._cell_proposal,
            target_week_id=request.target_week_id,
            target_section_key=request.target_section_key,
            reference_labels=request.reference_labels,
            valid_grounding_refs=request.valid_grounding_refs,
        )
