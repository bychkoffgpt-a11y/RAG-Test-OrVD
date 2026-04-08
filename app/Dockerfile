FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_EXTRA_INDEX_URL=
ARG PIP_TRUSTED_HOST=

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    tesseract-ocr \
    tesseract-ocr-rus \
    poppler-utils \
    ca-certificates \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml /app/
COPY src /app/src
COPY wheels /wheels

RUN set -euo pipefail; \
    if [ -n "$(find /wheels -mindepth 1 -maxdepth 1 -type f -name '*.whl' -print -quit)" ]; then \
      echo "[INFO] pip mode: offline wheels (/wheels)"; \
      pip install --no-index --find-links=/wheels --no-build-isolation . ; \
    else \
      echo "[WARN] pip mode: online PyPI (wheelhouse is empty)"; \
      python - <<'PY' \
import ssl, socket \
ctx = ssl.create_default_context() \
with socket.create_connection(("pypi.org", 443), timeout=10) as sock: \
    with ctx.wrap_socket(sock, server_hostname="pypi.org"): \
        pass \
print("[INFO] TLS precheck to pypi.org:443 passed") \
PY \
      || { \
        echo "[FAIL] TLS precheck to pypi.org:443 failed. Проверьте доступ в интернет, proxy и CA-сертификаты Docker host."; \
        exit 1; \
      }; \
      pip_args="--retries 10 --index-url=${PIP_INDEX_URL} --no-build-isolation"; \
      if [ -n "${PIP_EXTRA_INDEX_URL}" ]; then \
        pip_args="${pip_args} --extra-index-url=${PIP_EXTRA_INDEX_URL}"; \
      fi; \
      if [ -n "${PIP_TRUSTED_HOST}" ]; then \
        pip_args="${pip_args} --trusted-host=${PIP_TRUSTED_HOST}"; \
      fi; \
      # shellcheck disable=SC2086 \
      pip install ${pip_args} . \
      || { \
        echo "[FAIL] pip install не смог загрузить зависимости из индекса. Для закрытого контура подготовьте app/wheels и используйте офлайн-сборку."; \
        exit 1; \
      }; \
    fi


EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
