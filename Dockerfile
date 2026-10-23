FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY demo_data ./demo_data
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "roledock.api:app", "--host", "0.0.0.0", "--port", "8000"]
