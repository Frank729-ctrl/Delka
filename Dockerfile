FROM python:3.12-slim

# ── System dependencies for WeasyPrint + fonts ──────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev \
    libxml2 \
    libxslt1.1 \
    shared-mime-info \
    media-types \
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ──────────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── App source ───────────────────────────────────────────────────────────────
COPY . .
RUN mkdir -p logs

# ── Runtime ──────────────────────────────────────────────────────────────────
EXPOSE ${PORT:-8000}
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
