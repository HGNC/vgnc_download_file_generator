FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY src/ src/
COPY generate_all.sh entrypoint.sh ./
RUN chmod +x generate_all.sh entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
