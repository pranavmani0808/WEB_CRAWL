#!/bin/bash

# Start Celery Worker
# Run this in Terminal 2

set -e

echo "🔧 Starting Celery Worker..."
echo ""
echo "Worker is listening for tasks from Redis queue"
echo "Press Ctrl+C to stop"
echo ""

cd "$(dirname "$0")/backend"

# Verify .env file exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "Please copy .env.example to .env and update with your credentials:"
    echo "  cp .env.example .env"
    exit 1
fi

# Install dependencies if needed
if ! python3 -c "import celery" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip install -q -r requirements.txt
fi

# Start the worker
celery -A app.workers.celery_app worker --loglevel=info --concurrency=4
