FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app/ ./app/

RUN pip install --no-cache-dir -e .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://localhost:8000/health')" || exit 1

CMD ["ps2-mcp-server"]
