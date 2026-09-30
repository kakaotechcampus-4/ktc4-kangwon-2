"""이미지가 참조자료를 실제로 읽는지 본다. CI 의 docker 잡이 부른다.

**`import app.main` 만으로는 못 잡는다.** 참조자료는 `p0-planning/data/` 에 있고 그 폴더는
패키지 밖이라(`packages.find` 가 `src/` 만 본다) 설치 방식에 따라 이미지에서 사라진다.
그래도 import 는 멀쩡히 되고, **계획안을 만들 때** FileNotFoundError 로 죽는다.

파일이 있는지가 아니라 **읽어서 카탈로그가 나오는지**를 본다.
"""

from ssuksak.adapters.json_activity_reference_repository import _DATA as ACTIVITIES
from ssuksak.adapters.json_theme_reference_repository import JsonThemeReferenceRepository
from ssuksak.adapters.monthly_reference_repositories import _DATA as DATA

CATALOG_ID = "ssuksak.yearly-theme-reference"
CATALOG_VERSION = "theme-reference-v0.1.2"


def main() -> None:
    catalog = JsonThemeReferenceRepository().get_catalog(CATALOG_ID, CATALOG_VERSION)
    assert catalog is not None, f"{CATALOG_ID}/{CATALOG_VERSION} 을 읽지 못했다"
    assert ACTIVITIES.exists(), f"활동 자료가 없다: {ACTIVITIES}"
    assert (DATA / "rules").exists(), f"규칙 자료가 없다: {DATA / 'rules'}"
    print("참조자료 OK")


if __name__ == "__main__":
    main()
