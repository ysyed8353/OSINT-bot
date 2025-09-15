# Main OSINT Bot
Production-ready Telegram bot for OSINT queries

## Features
- Phone number lookups
- Vehicle information 
- Aadhaar details
- UPI ID searches
- Subscription management integration

## Deployment
- Deploy this folder as a separate Render service
- Uses @reosintbot token
- Health check on port 8000

## Environment Variables
```
TELEGRAM_BOT_TOKEN=your_main_bot_token
BOT_USERNAME=reosintbot
OSINT_API_BASE_URL=https://osint.stormx.pw/index.cpp
OSINT_API_KEY=dark
ADMIN_USER_ID=5682019164
PORT=8000
LOG_LEVEL=INFO
```