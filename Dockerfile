FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client default-libmysqlclient-dev build-essential pkg-config parallel \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY src/ src/
COPY db_query_helper.py ./
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
