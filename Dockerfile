FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client default-libmysqlclient-dev build-essential pkg-config parallel \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app

COPY vgnc-download-files/pyproject.toml vgnc-download-files/uv.lock vgnc-download-files/README.md ./
RUN uv sync --frozen --no-dev

COPY vgnc-download-files/src/ src/
COPY vgnc-download-files/db_query_helper.py ./
COPY vgnc-download-files/entrypoint.sh ./
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
