FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV KLOD_LOAD_MODEL=false
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir . && useradd --system --uid 10001 --create-home app && mkdir -p /app/data /data && chown -R app:app /app /data
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["sh", "/usr/local/bin/docker-entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn klod.api:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/healthz', timeout=3).read()"
