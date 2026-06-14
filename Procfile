
# Elastic Beanstalk uses this file to know what to run.
# EB only exposes ONE web process on port 8080 (proxied from 80).
# We run the Solar API as the primary "web" process on port 8080,
# and the Optimization API as a background "worker" on port 8001.

web: gunicorn main_solar_api:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8080 --timeout 120
