FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for psycopg and pandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc build-essential curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools wheel

# Layer 1: pre-install dependencies before copying source (maximises cache reuse)
# Python 3.11+ has tomllib built-in — parse deps directly from pyproject.toml
COPY pyproject.toml ./
RUN python3 -c "import tomllib,subprocess,sys; f=open('pyproject.toml','rb'); deps=tomllib.load(f)['project']['dependencies']; subprocess.check_call([sys.executable,'-m','pip','install']+deps)"

# Layer 2: copy source and install the package itself (no-deps: already installed above)
COPY . .
RUN pip install . --no-deps

# ── API target ─────────────────────────────────────────
FROM base AS api
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn plutus.api.main:app --host 0.0.0.0 --port 8000 --workers 2"]

# ── Scheduler target ───────────────────────────────────
FROM base AS scheduler
CMD ["python", "-m", "plutus.scheduler.runner"]
