FROM python:3.11-slim-bookworm

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Headless Chromium for JS-rendered (SPA) page audits. --with-deps pulls in
# the shared libraries chromium needs on slim-bookworm. Only the worker
# actually launches it; the api/beat services just carry the image weight.
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY . .

# Expose backend port
EXPOSE 8000

# Default command; docker-compose overrides this for worker/beat services.
# Railway injects $PORT at runtime, so use shell form to expand it.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
