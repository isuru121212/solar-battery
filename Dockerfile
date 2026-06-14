FROM python:3.11-slim

WORKDIR /app

# System deps for TensorFlow + PuLP
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    coinor-cbc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main_solar_api.py    .
COPY optimization_api.py  .

# Copy model files and data (local dev / non-S3 mode)
COPY models/  ./models/
COPY data/    ./data/

EXPOSE 8000 8001

# Default command (overridden by docker-compose)
CMD ["uvicorn", "main_solar_api:app", "--host", "0.0.0.0", "--port", "8000"]