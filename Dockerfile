FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libgdk-pixbuf-xlib-2.0-0 libharfbuzz0b \
    fontconfig fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY frontend /app/frontend

# Run as the host user's uid/gid (1000) so the mounted ./data stays writable
# by the operator instead of becoming root-owned.
RUN groupadd --gid 1000 packing && useradd --uid 1000 --gid 1000 --no-create-home packing \
    && mkdir -p /app/data && chown -R packing:packing /app
USER packing

WORKDIR /app/backend

EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:3001/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3001"]
