"""다른 feature 가 등록 양식을 찾는 창구 (docs/structure.md 「규칙」).

§4 연간 생성이 받은 `form_id` 를 plans 가 이걸로 검사한다 — forms 모델을 직접 import 하지 않는다.
"""

from sqlalchemy.orm import Session

from app.features.forms.models import Form


def find_own_form(session: Session, center_id: int | None, form_id: int) -> Form | None:
    """이 원의 양식이면 돌려주고, 없거나 남의 원 것이면 None 이다.

    둘을 가르지 않는다 — 남의 것이 있다는 사실도 알려주지 않는다(ADR-017).
    감춘 양식은 없는 것과 같다 — 새 계획안에 못 쓴다.
    감춘 양식까지 찾는 창구는 쓰는 쪽이 생길 때 만든다(ADR-026).
    """
    form = session.get(Form, form_id)
    if (
        form is None
        or center_id is None
        or form.center_id != center_id
        or form.hidden_at is not None
    ):
        return None
    return form
