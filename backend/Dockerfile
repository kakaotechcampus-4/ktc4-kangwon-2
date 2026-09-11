FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY resources ./resources

RUN pip install --upgrade pip && pip install .

# hwp5html(pyhwp)이 실행되는지, XSLT 처리에 필요한 lxml이 로드되는지 확인
RUN hwp5html --help >/dev/null && python -c "import lxml.etree"

# 컨테이너를 root 로 돌리지 않는다.
# uid 를 1000 으로 못박는 이유: 마이그레이션 생성이 호스트를 마운트해서 파일을 쓴다.
#   docker compose run --rm -v "$(pwd)/backend:/app" backend alembic revision ...
# root 면 그 파일이 호스트에 root 소유로 생겨 ubuntu 가 수정도 삭제도 못 한다.
# 서버의 ubuntu 가 uid 1000 이라 맞춘다.
RUN useradd -m -u 1000 app && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
