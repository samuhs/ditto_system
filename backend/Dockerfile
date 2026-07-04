FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
# Install with the "local" extra so the sentence-transformers embedders
# (e5, paraphrase) work in-container, not only the Gemini provider.
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir ".[local]"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
