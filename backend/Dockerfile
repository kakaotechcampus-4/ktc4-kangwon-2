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

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
