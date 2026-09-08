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
