"""교사 계정 (docs/api-spec.md §0).

**한 계정이 원 하나를 갖는다.** `center_id` 는 온보딩 1단계에서 원을 만들 때 채워진다 —
회원가입 시점에는 아직 원이 없으므로 nullable 이다.

원 하나에 교사가 여럿일 수 있다(같은 원의 다른 담임). 그래서 `users.center_id` 이고
`centers.owner_id` 가 아니다 — 후자면 원마다 주인이 한 명으로 고정된다.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(
        String(254), comment="로그인 아이디. RFC 5321 의 최대 길이가 254 다"
    )
    name: Mapped[str] = mapped_column(String(50), comment="교사 이름. 화면 인사말에 쓴다")
    # 해시와 salt 를 따로 둔다. 한 컬럼에 합치면 구분자 규칙을 우리가 또 만들어야 한다.
    password_hash: Mapped[bytes] = mapped_column(LargeBinary(64), comment="scrypt 해시")
    password_salt: Mapped[bytes] = mapped_column(LargeBinary(16), comment="계정마다 다르다")
    center_id: Mapped[int | None] = mapped_column(
        ForeignKey("centers.id"),
        index=True,
        comment="온보딩 1단계에서 원을 만들 때 채워진다. 회원가입 직후에는 NULL",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
