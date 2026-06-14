# 📝 GIT & DEPLOYMENT COMMANDS REFERENCE

## 🔧 First Time Setup (Do This Once)

### 1. Create GitHub Repository
```bash
# Go to https://github.com/new
# Create repository named: "solar-battery"
# Description: "Solar Power Prediction & Battery Optimization System"
# Make it Public
# Create!
```

### 2. Clone or Initialize Locally
```bash
# If cloning from GitHub
git clone https://github.com/YOUR_USERNAME/solar-battery.git
cd solar-battery

# OR if initializing existing folder
cd "f:\research papers\isuru\new_deploy"
git init
git remote add origin https://github.com/YOUR_USERNAME/solar-battery.git
```

### 3. First Commit & Push
```bash
# Add all files
git add .

# Commit
git commit -m "Initial commit - Solar battery optimization system"

# Push to GitHub
git branch -M main
git push -u origin main
```

---

## 📤 Deployment to GitHub (After Each Change)

### Simple 3-Step Push
```bash
# 1. Add changes
git add .

# 2. Commit with message
git commit -m "Your change description"

# 3. Push to GitHub
git push
```

**That's it! If auto-deploy is enabled on Railway, your app updates automatically!**

---

## 🔄 Common Git Workflows

### Update Single File
```bash
git add path/to/file.py
git commit -m "Updated file.py"
git push
```

### Update Multiple Files
```bash
git add .
git commit -m "Multiple updates"
git push
```

### Undo Last Commit (Before Push)
```bash
git reset --soft HEAD~1
```

### View Changes Before Committing
```bash
git status          # See what changed
git diff            # See detailed changes
```

### View Commit History
```bash
git log
git log --oneline   # Shorter format
```

---

## 🆕 Creating Branches (Advanced)

### Create New Branch
```bash
git checkout -b feature/new-feature
# Make changes
git add .
git commit -m "New feature"
git push -u origin feature/new-feature
```

### Switch Between Branches
```bash
git checkout main           # Switch to main
git checkout feature/xyz    # Switch to feature branch
```

### Merge Back to Main
```bash
git checkout main
git pull
git merge feature/new-feature
git push
```

---

## 🚀 Deployment Workflow

### After Making Code Changes
```
1. Test locally (if possible)
   cd "f:\research papers\isuru\new_deploy"
   python startup.py

2. Commit changes
   git add .
   git commit -m "Description of changes"

3. Push to GitHub
   git push

4. ✅ Automatic! Railway deploys within 2-5 minutes
```

### Check Deployment Status
```
1. Open Railway Dashboard
2. Click project
3. View "Deployments" tab
4. See if new deployment is running
5. Check "Logs" if there are errors
```

---

## 🔐 Managing Sensitive Information

### DON'T Commit These Files
```bash
.env                    # Environment variables
*.key, *.pem           # SSH keys
AWS_credentials.csv    # AWS credentials
.vscode/settings.json  # Personal settings
```

### These Are Already Ignored
```
# Check .gitignore file
cat .gitignore
```

### If You Accidentally Committed Secrets
```bash
# IMPORTANT: Change your passwords/keys immediately!

# Remove from Git history
git rm --cached .env
git commit -m "Remove .env"
git push

# Add to .gitignore
echo ".env" >> .gitignore
git add .gitignore
git commit -m "Add .env to gitignore"
git push
```

---

## 📋 Setup Environment Variables on Railway

### Via Railway Dashboard (Recommended)
```
1. Go to Railway project
2. Click service
3. Variables tab
4. Add:
   Key: USE_S3
   Value: false
5. Save
```

### Via Railway CLI
```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Set variable
railway variables set USE_S3=false

# View variables
railway variables
```

---

## 🆘 Troubleshooting Commands

### Check Git Status
```bash
git status      # See what's changed
git log         # See commit history
git remote -v   # See connected repositories
```

### Fix Common Issues

**Issue: "Nothing to commit"**
```bash
# You've already committed everything
# Just make changes and commit again
```

**Issue: "Rejected push"**
```bash
# Pull latest changes first
git pull
# Then push
git push
```

**Issue: "Permission denied"**
```bash
# Set up SSH key (or use HTTPS token)
# See: https://docs.github.com/en/authentication/
```

---

## 🔄 Full Deployment Cycle

```bash
# 1. Navigate to project
cd "f:\research papers\isuru\new_deploy"

# 2. Make changes to your files
# (edit Python files, dashboard, etc.)

# 3. Check what changed
git status

# 4. Stage changes
git add .

# 5. Commit
git commit -m "Updated dashboard UI"

# 6. Push to GitHub
git push

# 7. Watch Railway deploy!
# Go to: https://railway.app/dashboard
# Click project
# See new deployment running

# 8. Once deployed, view live app
# https://your-railway-url.railway.app
```

---

## 📱 Using Railway CLI (Power User Mode)

### Install Railway CLI
```bash
npm i -g @railway/cli
```

### Common Commands
```bash
# Login to Railway
railway login

# Link to project
railway link

# Deploy
railway up

# View logs (real-time)
railway logs -f

# View status
railway status

# Restart
railway restart

# View environment variables
railway variables
```

---

## 🎯 Quick Command Reference

| Task | Command |
|------|---------|
| Check status | `git status` |
| See changes | `git diff` |
| Stage all | `git add .` |
| Commit | `git commit -m "msg"` |
| Push | `git push` |
| View history | `git log --oneline` |
| Pull updates | `git pull` |
| Create branch | `git checkout -b name` |
| Switch branch | `git checkout name` |
| Delete branch | `git branch -d name` |

---

## ✅ Your Deployment Workflow

```
Edit Code
    ↓
git add .
    ↓
git commit -m "message"
    ↓
git push
    ↓
Railway auto-deploys (2-5 min)
    ↓
✅ Live on https://your-app.railway.app
```

---

## 📞 Need Help?

### Git Help
```bash
git help <command>
# Example: git help push
```

### GitHub Documentation
- https://docs.github.com/en/get-started

### Railway Documentation
- https://docs.railway.app/

---

**Now you're ready to deploy! Happy coding! 🚀**
