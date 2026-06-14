# 🚀 RAILWAY DEPLOYMENT GUIDE - Solar Battery Optimization System

**Status**: Production Ready  
**Estimated Time**: 15-30 minutes  
**Cost**: Pay-as-you-go (similar to before)  
**Difficulty**: ⭐ Easy (even simpler than AWS!)

---

## 📋 QUICK SUMMARY

Railway is perfect for your application:
- ✅ One-click deployment from GitHub
- ✅ Automatic Docker support
- ✅ Easy environment variables
- ✅ Auto-scaling included
- ✅ Free SSL/HTTPS
- ✅ Same pricing model as your previous deployment

---

## 🎯 STEP 1: Create Railway Account

### Option A: Sign Up via GitHub (Recommended)
```
1. Go to: https://railway.app/
2. Click "Start Free" button
3. Click "Continue with GitHub"
4. Authorize Railway to access your GitHub
5. Done! You're logged in
```

### Option B: Sign Up via Email
```
1. Go to: https://railway.app/
2. Click "Start Free"
3. Enter email and password
4. Verify email
5. Done!
```

**No credit card required for free tier**

---

## 🔧 STEP 2: Upload Code to GitHub (If Not Already)

### If your code is NOT on GitHub:

```bash
# Navigate to your project folder
cd "f:\research papers\isuru\new_deploy"

# Initialize git repository
git init

# Add all files
git add .

# Commit
git commit -m "Solar battery optimization system - ready for deployment"

# Create new repository on GitHub.com manually
# Then push:
git remote add origin https://github.com/YOUR_USERNAME/solar-battery.git
git branch -M main
git push -u origin main
```

**Get GitHub account**: https://github.com/signup (if you don't have one)

---

## 🚀 STEP 3: Deploy to Railway (3 Simple Steps)

### Step 1: Connect GitHub Repository
```
1. Go to: https://railway.app/dashboard
2. Click "New Project"
3. Select "Deploy from GitHub"
4. Choose your repository "solar-battery"
5. Click "Deploy Now"
```

### Step 2: Railway Auto-Detects Your App
```
✅ Detects Docker (from your Dockerfile)
✅ Builds automatically
✅ Starts services
✅ Takes 2-5 minutes
```

### Step 3: Add Environment Variables
```
1. Go to your project on Railway dashboard
2. Click the service (solar-battery)
3. Go to "Variables" tab
4. Add these variables:

Key: USE_S3
Value: false

Key: PYTHONUNBUFFERED
Value: true

Key: PORT
Value: 8080
```

**That's it! Railway handles everything else.**

---

## ✅ VERIFICATION: Check if Deployed

### View Your Live URL
```
1. Go to Railway Dashboard
2. Click your project
3. Click "Deployments"
4. Look for "Public URL" under the active deployment
5. Example: https://solar-battery-prod-xyz.railway.app
```

### Test Endpoints
```bash
# Replace with YOUR Railway URL
YOUR_URL="https://solar-battery-prod-xyz.railway.app"

# Test solar API
curl $YOUR_URL/api/solar/status

# Test optimization API
curl $YOUR_URL/api/opt/status

# Test health check
curl $YOUR_URL/health
```

### Access Your Dashboard
```
https://YOUR_RAILWAY_URL/
(Open in browser)
```

---

## 🔧 RAILWAY CONFIGURATION FILES

### Your Project Already Has These:
```
✅ Dockerfile          (Multi-service Docker setup)
✅ requirements.txt    (Python dependencies)
✅ docker-compose.yml  (Service configuration)
✅ Procfile.beanstalk  (Already compatible)
```

### Railway Uses Dockerfile Automatically
- Railway detects `Dockerfile`
- Builds and deploys automatically
- No additional config needed!

---

## 📊 WHAT RAILWAY PROVIDES

| Feature | Included |
|---------|----------|
| **Container Runtime** | ✅ Free (Docker) |
| **Domain** | ✅ Free (`*.railway.app`) |
| **SSL/HTTPS** | ✅ Free (auto-enabled) |
| **Scaling** | ✅ Automatic |
| **Monitoring** | ✅ Built-in logs |
| **Environment Variables** | ✅ Easy management |
| **Custom Domain** | ✅ $10/month (optional) |

---

## 💰 PRICING (Pay-as-you-go)

| Resource | Cost |
|----------|------|
| **Compute (vCPU)** | $0.000417/hour (~$10/month full time) |
| **Memory (GB)** | $0.0000579/hour (~$0.50/month per GB) |
| **Disk** | $0.0002315/GB/day (~$7/month per 100GB) |
| **Network (outbound)** | $0.02/GB (data transfer) |

**Estimated**: $15-25/month for full deployment

---

## 🛠️ STEP 4: Custom Domain (Optional)

If you want your own domain instead of `railway.app`:

### Setup Custom Domain
```
1. Buy domain from GoDaddy, Namecheap, etc.
2. Go to Railway project → "Settings"
3. Click "Add Domain"
4. Enter your domain: yourdomain.com
5. Update DNS records (Railway provides instructions)
6. Wait 5-10 minutes for SSL
```

**Cost**: $10/month + domain registration (~$12/year)

---

## 🔐 SECURITY & BEST PRACTICES

### 1. Keep API Keys Secret
```
❌ DON'T: Push .env or secrets to GitHub
✅ DO: Set variables in Railway dashboard
```

### 2. Enable Auto-Deploy
```
Railway Settings:
1. Go to "GitHub Integration"
2. Enable "Auto-deploy on push"
3. Now every Git push auto-deploys!
```

### 3. Manage Database (If Needed Later)
```
You can add PostgreSQL/MySQL from Railway dashboard:
1. New Service
2. PostgreSQL or MySQL
3. Auto-connects to your app
```

---

## 📝 ENVIRONMENT VARIABLES REFERENCE

If you need more advanced setup:

```
# For local S3 storage (disable S3 mode)
USE_S3=false

# For AWS S3 integration (if you want later)
USE_S3=true
S3_BUCKET=your-bucket-name
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx

# Application settings
PORT=8080
PYTHONUNBUFFERED=true
LOG_LEVEL=INFO

# API URLs (for merged app)
SOLAR_API_URL=http://localhost:8080/api/solar
OPT_API_URL=http://localhost:8080/api/opt
```

---

## 🚨 TROUBLESHOOTING

### Deployment Failed?

**Check 1: Build Logs**
```
1. Go to Railway dashboard
2. Click project
3. Click "Deployments"
4. Click failed deployment
5. Scroll down to see build error
6. Common errors:
   - Missing dependencies (add to requirements.txt)
   - Port conflicts (should be 8080)
   - Python version mismatch
```

**Check 2: Verify Dockerfile**
```bash
# Build locally first
docker build -t solar-battery:latest .

# Run locally
docker run -p 8080:8080 solar-battery:latest
```

**Check 3: Check Logs**
```
1. Railway dashboard → Logs tab
2. Look for error messages
3. Common issues:
   - "Module not found" → missing from requirements.txt
   - "Port already in use" → change PORT env var
   - "Connection refused" → services not starting
```

### App Won't Start?

**Solution 1: Increase Memory**
```
1. Railway dashboard → Settings
2. Increase allocated memory to 1GB
3. Restart deployment
```

**Solution 2: Check Environment Variables**
```
1. Verify all env vars are set
2. Make sure no typos
3. Restart the app
```

**Solution 3: View Real-time Logs**
```
1. Railway dashboard → Logs tab
2. Click "Live" to see real-time output
3. Check for error messages
```

---

## 📈 MONITORING & MANAGEMENT

### View Logs
```
1. Go to Railway project
2. Click "Logs" tab
3. View real-time application logs
4. Filter by service or time
```

### Monitor Performance
```
1. Go to project → "Metrics"
2. View CPU, Memory, Network usage
3. Check response times
4. Identify bottlenecks
```

### Restart Service
```
1. Go to project dashboard
2. Click service
3. Click "Restart" button
4. Service redeploys instantly
```

### Rollback to Previous Version
```
1. Go to Deployments
2. Click previous deployment
3. Click "Redeploy"
4. Service rolls back instantly
```

---

## 🔄 CONTINUOUS DEPLOYMENT

### Auto-Deploy on Every Git Push
```
1. Go to Railway project settings
2. Enable "Auto Deploy"
3. Connect to GitHub repository
4. Choose branch (main/master)
5. Now: Every git push → auto deployment!

# Example workflow:
git add .
git commit -m "Fix bug"
git push
# ✅ Automatically deploys to Railway!
```

### Manual Redeploy
```
1. Go to Railway dashboard
2. Click project
3. Click "Redeploy" button
4. Redeploys current code (2-5 minutes)
```

---

## 📊 PROJECT STRUCTURE FOR RAILWAY

Your current structure is **perfect for Railway**:

```
solar-battery/
├── Dockerfile              ← Railway uses this
├── docker-compose.yml      ← Reference (not needed on Railway)
├── requirements.txt        ← Dependencies
├── main_solar_api.py       ← Solar service
├── optimization_api.py     ← Optimization service
├── merged_app.py          ← Combined app (optional)
├── complete_dashboard.html ← Frontend
├── models/                ← ML models
├── data/                  ← Historical data
├── .gitignore            ← Ignore files
└── README.md             ← Documentation
```

---

## ✨ QUICK CHECKLIST

- [ ] Create Railway account
- [ ] Push code to GitHub
- [ ] Connect GitHub repo to Railway
- [ ] Railway auto-builds from Dockerfile
- [ ] Add environment variables
- [ ] Test public URL
- [ ] Access dashboard in browser
- [ ] Setup auto-deploy (optional)
- [ ] Add custom domain (optional)

---

## 🎉 DEPLOYMENT COMPLETE!

Once deployed, you have:

```
✅ Public URL (HTTPS)
✅ Auto-scaling
✅ Monitoring & logs
✅ Easy updates (git push)
✅ Automatic backups
✅ One-click rollback
✅ Custom domain support
```

---

## 📞 SUPPORT

### Railway Resources
- [Railway Docs](https://docs.railway.app/)
- [Railway Dashboard](https://railway.app/dashboard)
- [Discord Community](https://discord.gg/railway)

### Common Issues & Solutions
| Issue | Solution |
|-------|----------|
| App won't start | Check logs, increase memory |
| Port error | Use PORT env var = 8080 |
| Module not found | Add to requirements.txt |
| Slow response | Increase CPU/memory |
| Domain issues | Check DNS settings |

---

## 🚀 NEXT STEPS

1. **Create Railway account** (2 min)
2. **Push code to GitHub** (5 min)
3. **Deploy via Railway dashboard** (5 min)
4. **Add env variables** (2 min)
5. **Test deployment** (2 min)
6. **Configure custom domain** (optional, 10 min)
7. **Enable auto-deploy** (optional, 2 min)

**Total Time: 15-30 minutes**

---

## 💡 PRO TIPS

### Tip 1: Use Railway CLI for Advanced Control
```bash
# Install Railway CLI
npm i -g @railway/cli

# Login to Railway
railway login

# Deploy from command line
railway up

# View logs
railway logs
```

### Tip 2: Environment-Specific Variables
```
Development:  USE_S3=false
Production:   USE_S3=true (if using S3)
```

### Tip 3: Monitor in Production
```
1. Set up log alerts
2. Monitor error rates
3. Check response times daily
4. Scale if needed
```

### Tip 4: Backup Data
```
If using database:
1. Enable automatic backups
2. Export data weekly
3. Store safely
```

---

**Ready to deploy? Start with Step 1 above! 🚀**

**Questions? Check Railway docs or contact their support team.**

