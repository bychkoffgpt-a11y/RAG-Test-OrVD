# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_EXTRA_INDEX_URL=
ARG PIP_TRUSTED_HOST=
ARG PIP_MODE=auto
ARG PIP_ONLINE_FALLBACK=1
ARG INCLUDE_INGEST_DEPS=0

RUN set -euo pipefail; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      wget; \
    if [ "${INCLUDE_INGEST_DEPS}" = "1" ]; then \
      apt-get install -y --no-install-recommends \
        libreoffice \
        tesseract-ocr \
        tesseract-ocr-rus \
        poppler-utils; \
    fi; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml /app/
COPY wheels /wheels

RUN python - <<'PY'
import pathlib
import tomllib

pyproject_path = pathlib.Path('/app/pyproject.toml')
with pyproject_path.open('rb') as fh:
    data = tomllib.load(fh)

deps = list(data.get('project', {}).get('dependencies', []))
build_deps = list(data.get('build-system', {}).get('requires', []))
requirements = deps + build_deps
pathlib.Path('/tmp/requirements.txt').write_text('\n'.join(requirements) + '\n', encoding='utf-8')
PY

RUN --mount=type=cache,target=/root/.cache/pip \
    set -euo pipefail; \
    install_from_wheels() { \
      python3 -m pip install --no-index --find-links=/wheels --no-build-isolation -r /tmp/requirements.txt; \
    }; \
    install_from_index() { \
      python -c "import socket, ssl; ctx = ssl.create_default_context(); sock = socket.create_connection(('pypi.org', 443), timeout=10); wrapped = ctx.wrap_socket(sock, server_hostname='pypi.org'); wrapped.close(); print('[INFO] TLS precheck to pypi.org:443 passed')"; \
      pip_args="--retries 10 --index-url=${PIP_INDEX_URL} --no-build-isolation -r /tmp/requirements.txt"; \
      if [ -n "${PIP_EXTRA_INDEX_URL}" ]; then \
        pip_args="${pip_args} --extra-index-url=${PIP_EXTRA_INDEX_URL}"; \
      fi; \
      if [ -n "${PIP_TRUSTED_HOST}" ]; then \
        pip_args="${pip_args} --trusted-host=${PIP_TRUSTED_HOST}"; \
      fi; \
      # shellcheck disable=SC2086 \
      python3 -m pip install ${pip_args}; \
    }; \
    has_wheels=0; \
    if find /wheels -mindepth 1 -maxdepth 1 -type f -name '*.whl' -print -quit | grep -q .; then \
      has_wheels=1; \
    fi; \
    if [ "${PIP_MODE}" = "offline" ]; then \
      echo "[INFO] pip mode: forced offline (PIP_MODE=offline)"; \
      install_from_wheels || { \
        echo "[FAIL] Offline-установка не удалась: wheelhouse неполный или несовместимый."; \
        exit 1; \
      }; \
    elif [ "${PIP_MODE}" = "online" ]; then \
      if [ "$has_wheels" -eq 1 ]; then \
        if [ "${PIP_ONLINE_FALLBACK}" = "0" ]; then \
          echo "[INFO] pip mode: online strict wheels (PIP_MODE=online, no fallback)"; \
        else \
          echo "[INFO] pip mode: online with local wheelhouse preference (PIP_MODE=online)"; \
        fi; \
        install_from_wheels || { \
          if [ "${PIP_ONLINE_FALLBACK}" = "0" ]; then \
            echo "[FAIL] Установка из wheelhouse не удалась, а fallback в онлайн-индекс запрещён (PIP_ONLINE_FALLBACK=0)."; \
            exit 1; \
          else \
            echo "[WARN] Установка из wheelhouse не удалась. Переключаюсь на онлайн-индекс."; \
            install_from_index || { \
              echo "[FAIL] pip install не смог загрузить зависимости ни из wheelhouse, ни из индекса."; \
              exit 1; \
            }; \
          fi; \
        }; \
      else \
        echo "[INFO] pip mode: online (wheelhouse empty)"; \
        install_from_index || { \
          echo "[FAIL] pip install не смог загрузить зависимости из индекса."; \
          exit 1; \
        }; \
      fi; \
    elif [ "$has_wheels" -eq 1 ]; then \
      echo "[INFO] pip mode: auto -> offline wheels"; \
      install_from_wheels || { \
        echo "[WARN] Установка из wheelhouse не удалась. Переключаюсь на онлайн-индекс (PIP_MODE=auto)."; \
        install_from_index || { \
          echo "[FAIL] pip install не смог загрузить зависимости ни из wheelhouse, ни из индекса."; \
          exit 1; \
        }; \
      }; \
    else \
      echo "[INFO] pip mode: auto -> online index (wheelhouse is empty)"; \
      install_from_index || { \
        echo "[FAIL] pip install не смог загрузить зависимости из индекса."; \
        exit 1; \
      }; \
    fi

COPY src /app/src
RUN python3 -m pip install --no-deps --no-build-isolation .

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
