# ☀️⚡ Solar + Battery Optimization System

A real-time solar power prediction and battery optimization system with a beautiful web dashboard.

## 🎯 Features

- **Solar Power Predictions**: 24-hour ahead forecasts using TensorFlow ML model
- **Battery Optimization**: Real-time optimization of battery charging/discharging using linear programming
- **Interactive Dashboard**: Beautiful web UI for monitoring and control
- **Real-time Measurements**: Add solar measurements and update predictions
- **Cost Optimization**: Minimize electricity costs using time-of-use tariffs
- **Export Results**: Download optimization schedules as CSV

## 🚀 Quick Start

### Deployed Version (Easiest)
Open your Railway URL to access the live dashboard:
```
https://your-railway-url.railway.app/
```

### Local Development
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the application
python startup.py

# 3. Open in browser
http://localhost
```

### Docker
```bash
# Build
docker build -t solar-battery .

# Run
docker-compose up

# Access
http://localhost
```

## 📁 Project Structure

```
.
├── main_solar_api.py           # Solar prediction API (port 8000)
├── optimization_api.py         # Battery optimization API (port 8001)
├── merged_app.py              # Combined API (for single-instance deploy)
├── complete_dashboard.html     # Web dashboard (frontend)
├── startup.py                 # Local development launcher
├── Dockerfile                 # Docker configuration
├── docker-compose.yml         # Multi-service orchestration
├── requirements.txt           # Python dependencies
├── models/                    # ML models (TensorFlow)
├── data/                      # Historical data for training
└── README.md                  # This file
```

## 🔌 API Endpoints

### Solar Prediction API (http://localhost:8000)
```
GET  /                          # Welcome message
GET  /status                    # API status & initialization
GET  /predict                   # Get 24-hour solar predictions
POST /initialize               # Initialize with historical data
POST /update/realtime          # Add real-time measurement
```

### Battery Optimization API (http://localhost:8001)
```
GET  /                          # Welcome message
GET  /status                    # API status
GET  /config/battery           # Get current battery config
POST /config/battery           # Update battery config
GET  /tariff/default           # Get default time-of-use tariff
POST /optimize                 # Run optimization
```

### Combined API (http://localhost:8080 - for merged deployment)
```
GET  /                          # List all endpoints
GET  /health                    # Health check
GET  /api/solar/...            # All solar endpoints
GET  /api/opt/...              # All optimization endpoints
```

## 💻 Technology Stack

- **Backend**: FastAPI (Python)
- **ML Model**: TensorFlow/Keras
- **Optimization**: PuLP (Linear Programming)
- **Frontend**: HTML5 + Chart.js
- **Deployment**: Docker + Railway/AWS/EC2
- **Data Processing**: Pandas + NumPy

## 🔧 Configuration

### Environment Variables

```bash
# Use local files (default)
USE_S3=false

# Use AWS S3 (optional)
USE_S3=true
S3_BUCKET=your-bucket-name
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx

# Application settings
PORT=8080
PYTHONUNBUFFERED=true
LOG_LEVEL=INFO
```

### Battery Parameters (Configurable)

```
- Capacity: 100 kWh (default)
- Max Charge: 25 kW
- Max Discharge: 25 kW
- SOC Min: 20%
- SOC Max: 90%
- Efficiency: 95%
```

## 📊 Data Flow

```
Historical Data (CSV)
        ↓
  [Feature Engineering]
        ↓
  [ML Model Training]
        ↓
  [Solar Predictions]
        ↓
  [Real-time Measurements]
        ↓
  [Battery Optimization]
        ↓
  [Dashboard Visualization]
```

## 🌐 Deployment

### Railway (Recommended)
1. Push to GitHub
2. Connect to Railway
3. Deploy (automatic)
4. View at `https://your-app.railway.app`

See `RAILWAY_DEPLOYMENT.md` for detailed steps.

### AWS
- **Elastic Beanstalk**: Easy managed deployment
- **ECS/Fargate**: Containerized scalability
- **EC2**: Full control

See `AWS_DEPLOYMENT_COMPLETE.md` for detailed steps.

### Local Docker
```bash
docker-compose up
```

## 📈 Performance

- **Solar Predictions**: <100ms response time
- **Optimization Run**: 1-5 seconds (24-hour horizon)
- **Dashboard**: Full load <2 seconds
- **Throughput**: 100+ requests/second per instance

## 🔐 Security

- CORS enabled for cross-origin requests
- Environment variables for secrets
- HTTPS on Railway (automatic)
- No hardcoded credentials
- Rate limiting ready (add if needed)

## 📝 Example Usage

### 1. Load Sample Data
```bash
curl -X POST http://localhost:8000/initialize \
  -H "Content-Type: application/json" \
  -d '{"csv_path": "data/historical/historical_solar_data.csv"}'
```

### 2. Get Predictions
```bash
curl http://localhost:8000/predict
```

### 3. Run Optimization
```bash
curl -X POST http://localhost:8001/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "load_demand": [5,5,5,5,5,6,7,8,9,10,11,12,11,10,9,8,7,6,5,5,5,5,5,5],
    "hours": 24
  }'
```

## 🐛 Troubleshooting

### Issue: "Module not found"
**Solution**: Install dependencies
```bash
pip install -r requirements.txt
```

### Issue: "Port already in use"
**Solution**: Use different port
```bash
# Set PORT environment variable
export PORT=8080
python startup.py
```

### Issue: "Model files not found"
**Solution**: Check models directory
```bash
ls -la models/
# Should see: final_model_20250928_225759.keras, etc.
```

### Issue: "API won't respond"
**Solution**: Check logs
```bash
# Railway logs
railway logs

# Local logs
python startup.py
```

## 📚 Documentation

- [Railway Deployment](RAILWAY_DEPLOYMENT.md) - Easy one-click deployment
- [AWS Deployment](AWS_DEPLOYMENT_COMPLETE.md) - Complete AWS setup guide
- [Readiness Report](AWS_DEPLOYMENT_READINESS.md) - Technical analysis
- [API Documentation](API_DOCS.md) - Detailed API reference (if available)

## 🤝 Contributing

Feel free to submit issues and enhancement requests!

## 📄 License

This project is available for research and educational purposes.

## 👨‍💻 Author

Solar Battery Optimization Team - 2026

## 📞 Support

### For Railway Issues
- [Railway Docs](https://docs.railway.app)
- [Railway Discord](https://discord.gg/railway)

### For Technical Issues
1. Check the troubleshooting section above
2. Review logs in deployment platform
3. Check API health status endpoint

## 🎯 Next Steps

1. **Deploy to Railway**: Follow [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md)
2. **Access Dashboard**: Open your Railway URL in browser
3. **Test APIs**: Use the Dashboard UI or curl commands
4. **Customize**: Update battery parameters as needed
5. **Monitor**: Check Railway dashboard for performance

---

**Happy optimizing! ⚡☀️**
