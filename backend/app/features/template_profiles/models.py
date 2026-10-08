"""월간 TemplateProfile 버전 행과 원 기본 · 반 override 포인터 (Contract 2, 결정 문서 C2.6 · C2.8).

**Profile 은 원 소유다.** 여러 반 · 여러 학년도가 같은 READY 버전을 같이 가리킨다. 반마다
복제하지 않는다.

**기본 · override 는 Profile 의 상태가 아니라 포인터다.** READY 는 불변이라 「기본이다」를
Profile 행에 적으면 기본을 바꿀 때마다 READY 를 고치게 된다. 포인터는 정확한
`(profile_id, profile_version)` 하나를 가리키고, 새 READY 가 생겨도 움직이지 않는다.

포인터의 대상 조건 중 「같은 원 · 같은 문서 종류 · 존재하는 버전」은 **복합 FK 가 보장한다**
(`uq_template_profiles_owner_ref`). 「READY 인가」 「classroom_ref 가 비었나」는 상태라 FK 로
못 건다 — repository 가 본다.

본문은 plans 와 같은 방식이다 — Core `TemplateProfile` 전체를 `body` JSONB 에 담고 조회에
쓰는 값만 칸으로 꺼낸다. 꺼낸 칸은 body 에서 유도한다.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# 문서 종류 어휘는 plans.kind 를 따른다. Core 에 TemplateProfile 이 있는 것은 월간뿐이다.
DOC_KINDS = ("monthly",)
STATUSES = ("DRAFT", "READY", "ARCHIVED")

_TARGET = ("center_id", "doc_kind", "profile_id", "profile_version")
_TARGET_REF = tuple(f"template_profiles.{column}" for column in _TARGET)


class TemplateProfileVersion(Base):
    """Profile 버전 하나. 지우지 않는다 — 과거 계획안의 Snapshot lineage 가 가리킨다."""

    __tablename__ = "template_profiles"
    __table_args__ = (
        # Core 가 `(profile_id, profile_version)` 하나로 찾는다(ports.TemplateProfileRepository).
        UniqueConstraint("profile_id", "profile_version"),
        # 포인터 복합 FK 의 대상. 위 제약이 이미 유일하게 하지만 FK 는 이 칸들 그대로를 요구한다.
        UniqueConstraint(*_TARGET, name="uq_template_profiles_owner_ref"),
        CheckConstraint("doc_kind IN ('monthly')", name="doc_kind"),
        CheckConstraint("status IN ('DRAFT','READY','ARCHIVED')", name="status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    center_id: Mapped[int] = mapped_column(
        ForeignKey("centers.id"), index=True, comment="소유 원. body 의 institution_ref 와 같다"
    )
    doc_kind: Mapped[str] = mapped_column(String(10), comment="monthly")
    profile_id: Mapped[str] = mapped_column(
        String(64), comment="Profile 계열. 한 원에 속한다. body 의 profile_ref 와 같다"
    )
    profile_version: Mapped[str] = mapped_column(String(20), comment="v1, v2, ...")
    status: Mapped[str] = mapped_column(
        String(10), comment="DRAFT(편집 중) | READY(불변) | ARCHIVED(목록에서 숨김)"
    )
    parent_version: Mapped[str | None] = mapped_column(
        String(20), comment="이 DRAFT 를 파생시킨 READY 버전. Reference 기반 시작은 null"
    )
    body: Mapped[dict] = mapped_column(
        JSONB, comment="Core TemplateProfile 전체. 이것이 원본이고 위 칸들은 여기서 유도한다"
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), comment="이 버전을 만든 계정")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TemplateProfileDefault(Base):
    """원 기본 포인터. (원, 문서 종류)당 하나."""

    __tablename__ = "template_profile_defaults"
    __table_args__ = (
        ForeignKeyConstraint(_TARGET, _TARGET_REF, name="fk_template_profile_defaults_target"),
    )

    center_id: Mapped[int] = mapped_column(ForeignKey("centers.id"), primary_key=True)
    doc_kind: Mapped[str] = mapped_column(String(10), primary_key=True)
    profile_id: Mapped[str] = mapped_column(String(64))
    profile_version: Mapped[str] = mapped_column(String(20))
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), comment="마지막으로 바꾼 계정")
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TemplateProfileOverride(Base):
    """반 override 포인터. (classes.id, 문서 종류)당 하나. classes.id 가 학년도를 가른다."""

    __tablename__ = "template_profile_overrides"
    __table_args__ = (
        ForeignKeyConstraint(_TARGET, _TARGET_REF, name="fk_template_profile_overrides_target"),
    )

    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), primary_key=True)
    doc_kind: Mapped[str] = mapped_column(String(10), primary_key=True)
    center_id: Mapped[int] = mapped_column(
        ForeignKey("centers.id"), index=True, comment="반의 원. 대상 Profile 도 이 원 것이어야 한다"
    )
    profile_id: Mapped[str] = mapped_column(String(64))
    profile_version: Mapped[str] = mapped_column(String(20))
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), comment="마지막으로 바꾼 계정")
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
