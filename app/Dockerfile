FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    tesseract-ocr \
    tesseract-ocr-rus \
    poppler-utils \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml /app/
COPY src /app/src
COPY wheels /wheels

RUN if [ -n "$(find /wheels -mindepth 1 -maxdepth 1 -type f -name '*.whl' -print -quit)" ]; then \
      pip install --no-index --find-links=/wheels --no-build-isolation . ; \
    else \
      pip install --retries 10 --no-build-isolation . ; \
    fi


EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
