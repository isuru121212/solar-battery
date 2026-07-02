FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System deps: curl for healthcheck, coinor-cbc for PuLP solver
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    coinor-cbc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main_solar_api.py        .
COPY optimization_api.py      .
COPY inverter_monitor.py      .
COPY complete_dashboard.html  .
COPY start.sh                 .
RUN chmod +x start.sh
# Copy backtest results if they exist (generated locally by backtest.py)
COPY backtest_results.cs[v] ./

# Copy model files and data
COPY models/ ./models/
COPY data/   ./data/

# Railway injects $PORT at runtime; expose it symbolically
EXPOSE 8000

# start.sh launches both APIs; Solar API binds to $PORT (Railway public port)
CMD ["/app/start.sh"]