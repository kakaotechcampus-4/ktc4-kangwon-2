"""평가 점검 모델. 계약은 docs/api-spec.md §12, ADR-022 결정 6·7 · ADR-074 이다."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EvaluationCheck(Base):
    """원·학년도·평가요소마다 남기는 체크 시각(§12 · ADR-022 결정 6·7).

    줄이 있으면 체크된 상태이고, 풀면 그 줄을 지운다.
    누가 체크했는지는 남기지 않는다. 지난 학년도 줄은 보존한다.
    """

    __tablename__ = "evaluation_checks"
    __table_args__ = (UniqueConstraint("center_id", "school_year", "element"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("centers.id"))
    school_year: Mapped[int]
    element: Mapped[str] = mapped_column(String(20), comment="평가요소 키 — 예: 6-3-1")
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), comment="☐ 에서 ☑ 로 바뀐 시각"
    )


class EvaluationDocMark(Base):
    """교사가 챙기는 평가 서류 6종의 도장 근거 가운데 교사 몫(ADR-074 결정 3 · 4 · 5).

    원 · 학년도 · **교사** · 서류마다 한 줄이다.
    직접확인 시각과 그 교사의 마지막 폴더 검사 결과(상태 · 기간 · 건수 둘)를 둔다.
    둘 다 비면 줄을 지운다. **파일 이름 · 경로 · 아동 실명은 두지 않는다**(ADR-013 · ADR-045).
    쌤플확정은 저장하지 않는다 — 확정 문서에서 그때그때 센다.
    """

    __tablename__ = "evaluation_doc_marks"
    __table_args__ = (UniqueConstraint("center_id", "school_year", "user_id", "doc"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("centers.id"))
    school_year: Mapped[int]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    doc: Mapped[str] = mapped_column(String(20), comment="서류 키 — 예: parent")
    checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="직접확인을 누른 시각. 쌤플이 만들지 않는 서류만 있다",
    )
    folder_status: Mapped[str | None] = mapped_column(
        String(10), comment="마지막 폴더 검사 결과 — found · partial · missing"
    )
    folder_scanned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="폴더를 고른 시각"
    )
    folder_from: Mapped[date | None] = mapped_column(Date, comment="폴더 검사 기간 첫날")
    folder_to: Mapped[date | None] = mapped_column(Date, comment="폴더 검사 기간 마지막 날")
    # 숫자 둘만 둔다 — 다시 열어도 근거 줄이 같게
    # (「이름으로 찾음 · 2건」 · 「일부 빠짐 · 빈 평일 3일」).
    # 어느 날이 비었는지 · 파일 이름은 두지 않는다(사용자 결정 2026-11-09 · ADR-074 결정 5).
    folder_files: Mapped[int | None] = mapped_column(comment="폴더 검사에서 이름으로 센 파일 수")
    folder_gaps: Mapped[int | None] = mapped_column(comment="폴더 검사에서 빈 평일 · 빈 달 수")


class EvaluationDirectorCheck(Base):
    """원장님이 챙기는 서류 5가지의 체크 — 원 · 학년도 · 항목마다 한 줄(ADR-074 결정 4).

    같은 원 교사 누구나 같은 체크를 본다(자체평가 체크와 같은 모양, ADR-022 결정 6).
    풀면 줄을 지운다.
    """

    __tablename__ = "evaluation_director_checks"
    __table_args__ = (UniqueConstraint("center_id", "school_year", "item"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(ForeignKey("centers.id"))
    school_year: Mapped[int]
    item: Mapped[str] = mapped_column(String(20), comment="원장 서류 키 — 예: annual-plan")
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), comment="☐ 에서 ☑ 로 바뀐 시각"
    )
