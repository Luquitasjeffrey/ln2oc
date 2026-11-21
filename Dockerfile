# --- Stage 1: generate LND gRPC stubs from the vendored, version-pinned protos ---
FROM python:3.12-slim AS protos
WORKDIR /build
RUN pip install --no-cache-dir grpcio-tools==1.85.3
COPY proto/ ./proto/
COPY scripts/gen_protos.sh ./scripts/
RUN mkdir app && PYTHON=python scripts/gen_protos.sh

# --- Stage 2: runtime ---
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY --from=protos /build/app/lnrpc ./app/lnrpc

# Run as an unprivileged user whose uid can read the mounted macaroon (LND files are 0640).
ARG APP_UID=1000
RUN useradd --system --uid ${APP_UID} ln2oc && mkdir -p /data && chown ln2oc /data
USER ln2oc

EXPOSE 8000

# Exactly ONE process: the worker takes an exclusive file lock, a second one refuses to start.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
