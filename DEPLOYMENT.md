# Main OSINT Bot Deployment Guide

## 🚀 Render.com Deployment

### Prerequisites
1. GitHub repository with this folder's code
2. Telegram bot token from @BotFather for @reosintbot

### Step 1: Create Render Service
1. Go to Render.com dashboard
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. **Important**: Select this folder (`osint-main-bot`) as the root directory

### Step 2: Service Configuration
- **Name**: `osint-main-bot`
- **Environment**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python main.py`
- **Plan**: Free
- **Health Check Path**: `/health`

### Step 3: Environment Variables
Set these in Render dashboard:
```
PYTHONUNBUFFERED=1
PORT=8000
TELEGRAM_BOT_TOKEN=your_main_bot_token
BOT_USERNAME=reosintbot
OSINT_API_BASE_URL=https://osint.stormx.pw/index.cpp
OSINT_API_KEY=dark
ADMIN_USER_ID=5682019164
LOG_LEVEL=INFO
```

### Step 4: Deploy
1. Click "Create Web Service"
2. Wait for deployment
3. Check health: `https://your-service.onrender.com/health`

## ✅ Success Indicators
- Service shows "Live" status
- Health endpoint returns JSON with "healthy": true
- No "Conflict" errors in logs
- Bot responds to Telegram messages

## 🔧 Local Testing
```bash
# Copy environment file
cp .env.example .env
# Edit .env with your tokens

# Install dependencies
pip install -r requirements.txt

# Run bot
python main.py
```