FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# PDF 내보내기 글꼴 (ADR-061). hwpx_pdf.FONT_CANDIDATES 가 나눔고딕을 이 경로에서 찾는다.
# 없으면 PDF 만 503 이고 hwpx · hwp 는 그대로 나간다.
RUN apt-get update && apt-get install -y --no-install-recommends fonts-nanum     && rm -rf /var/lib/apt/lists/*

# 빌드 맥락이 backend/ 가 아니라 저장소 뿌리다. 계획안 생성 로직이 p0-planning 에
# 있어서 backend 만으로는 이미지가 앱을 import 하지 못한다.
#
# p0-planning 을 **먼저** 깐다. 그래야 아래 backend 설치에서 ssuksak-planning 이
# 이미 충족된 것으로 잡혀 PyPI 를 보러 가지 않는다 (거기엔 이 이름이 없다).
#
# **-e 로 깐다.** 참조자료가 p0-planning/data/ 에 있는데 이 폴더는 패키지 밖이라
# (pyproject 의 packages.find 가 src/ 만 본다) 비편집 설치면 같이 안 따라온다.
# 그 상태에서 어댑터의 Path(__file__).parents[3] 가 site-packages 위를 가리켜
# data/themes/theme_reference_v0.json 을 못 찾는다 — 계획안 생성이 FileNotFoundError 로
# 죽는다. -e 면 소스 트리를 그대로 가리키므로 /app/p0-planning/data 가 잡힌다.
# backend 쪽도 같은 이유로 CI 가 -e 를 쓴다(.github/workflows/ci.yml).
COPY p0-planning ./p0-planning
RUN pip install --upgrade pip && pip install -e ./p0-planning

COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/resources ./resources

RUN pip install .

# 서버에서 손으로 · cron 으로 돌리는 스크립트다 — ADR-088 사본 재대조(`recheck_observation_snapshots.py`) 같은 것.
# 문서가 `docker compose exec backend python scripts/…` 로 적어 두었는데 이 줄이 없으면 파일이 없다.
# 100KB 남짓이라 폴더째 넣는다. pip 설치 뒤에 두어 스크립트만 바뀌면 설치 층을 다시 쓰지 않는다.
COPY backend/scripts ./scripts

# hwp5html(pyhwp)이 실행되는지, XSLT 처리에 필요한 lxml이 로드되는지,
# PDF 내보내기가 한글 글꼴을 찾는지 확인
RUN hwp5html --help >/dev/null && python -c "import lxml.etree"     && python -c "from app.shared.hwpx_pdf import _register_fonts; _register_fonts()"

# 컨테이너를 root 로 돌리지 않는다.
# uid 를 1000 으로 못박는 이유: 마이그레이션 생성이 호스트를 마운트해서 파일을 쓴다.
#   docker compose run --rm -v "$(pwd)/backend:/app" backend alembic revision ...
# root 면 그 파일이 호스트에 root 소유로 생겨 ubuntu 가 수정도 삭제도 못 한다.
# 서버의 ubuntu 가 uid 1000 이라 맞춘다.
RUN useradd -m -u 1000 app && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
