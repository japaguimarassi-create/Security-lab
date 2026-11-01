FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
ENV KLOD_LOAD_MODEL=false
EXPOSE 8000
CMD ["uvicorn", "klod.api:app", "--host", "0.0.0.0", "--port", "8000"]
