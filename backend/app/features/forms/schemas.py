from pydantic import BaseModel


class Cell(BaseModel):
    text: str
    rowspan: int
    colspan: int


# 표 하나 = 행(row)의 리스트, 행 하나 = 셀(Cell)의 리스트
Table = list[list[Cell]]


class ParseResponse(BaseModel):
    filename: str
    tables: list[Table]
    labels: list[str]
    # 라벨 -> 표준 행 이름(예: "주제" -> "topic"). 데이터 값이거나 매핑표에
    # 없는 표현이면 값이 null. mapping.py 의 resources/forms/label_mapping.json 참고.
    label_map: dict[str, str | None]
