"""
OSINT Telegram Bot
A Telegram bot for performing OSINT (Open Source Intelligence) lookups
Production-ready version with enhanced error handling and validation
"""

import os
import logging
import re
import ipaddress
import sys
import asyncio
import time
from typing import Optional, Dict, Any
from datetime import datetime
import validators
import requests
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from subscription_manager import SubscriptionManager

# Load environment variables
load_dotenv()

# Production environment validation
def validate_environment():
    """Validate all required environment variables for production"""
    required_vars = [
        'TELEGRAM_BOT_TOKEN',
        'BOT_USERNAME',
        'OSINT_API_BASE_URL',
        'OSINT_API_KEY'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logging.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        print(f"ERROR: Missing required environment variables: {', '.join(missing_vars)}")
        print("Please check your .env file and ensure all required variables are set.")
        sys.exit(1)
    
    # Validate API URL
    api_url = os.getenv('OSINT_API_BASE_URL')
    if not validators.url(api_url):
        logging.error(f"Invalid OSINT_API_BASE_URL: {api_url}")
        sys.exit(1)
    
    logging.info("Environment validation passed")

# Validate environment on startup
validate_environment()

# Configure logging for production
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
log_level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO'))

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    format=log_format,
    level=log_level,
    handlers=[
        logging.FileHandler('logs/osint_bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class OSINTBot:
    """OSINT Telegram Bot class with production features"""
    
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.bot_username = os.getenv('BOT_USERNAME', 'reosintbot')
        self.api_base_url = os.getenv('OSINT_API_BASE_URL', 'https://osint.stormx.pw/index.php')
        self.api_key = os.getenv('OSINT_API_KEY', 'dark')
        self.start_time = datetime.now()
        self.is_healthy = True
        self.health_server = None
        
        # Request session for connection pooling
        self.session = requests.Session()
        self.session.timeout = 30  # 30 second timeout
        
        # Initialize subscription manager
        self.subscription_manager = SubscriptionManager(
            admin_username="ded_xdk",  # Admin contact for subscriptions
            admin_id=int(os.getenv('ADMIN_USER_ID', '5682019164'))
        )
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors in the bot"""
        logger.error(f"Exception while handling an update: {context.error}")
        
        # Handle specific Telegram conflicts
        if "Conflict" in str(context.error):
            logger.error("Bot conflict detected - another instance may be running with the same token")
            self.is_healthy = False
            # Don't retry on conflicts - let it fail
            return
        
        # Handle other errors gracefully
        if update and hasattr(update, 'effective_message') and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "❌ An error occurred while processing your request. Please try again later."
                )
            except Exception as e:
                logger.error(f"Failed to send error message: {e}")
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")
    
    def validate_input(self, query: str) -> Dict[str, Any]:
        """
        Validate and categorize the input query for StormX OSINT APIs
        
        Args:
            query (str): The input to validate
            
        Returns:
            Dict containing validation result and input type
        """
        query = query.strip()
        
        if not query:
            return {"valid": False, "error": "Empty input provided"}
        
        # Check if it's a phone number (Indian format - 10 digits)
        if re.match(r'^\d{10}$', query):
            return {"valid": True, "type": "phone", "value": query}
        
        # Check if it's a phone number with country code (+91 followed by 10 digits)
        if re.match(r'^\+91\d{10}$', query):
            return {"valid": True, "type": "phone", "value": query[3:]}  # Remove +91
        
        # Check if it's an Aadhaar number (12 digits)
        if re.match(r'^\d{12}$', query):
            return {"valid": True, "type": "aadhaar", "value": query}
        
        # Check if it's a vehicle number (Indian format)
        # Formats like: JK05F1806, DL1CAB1234, etc.
        if re.match(r'^[A-Z]{2}\d{1,2}[A-Z]{0,2}\d{4}$', query.upper()):
            return {"valid": True, "type": "vehicle", "value": query.upper()}
        
        # Check if it's a UPI ID (contains @ symbol)
        if "@" in query and re.match(r'^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+$', query):
            # Check if it looks like an email vs UPI
            if query.endswith(('.com', '.org', '.net', '.edu', '.gov')):
                return {"valid": True, "type": "email", "value": query}
            else:
                return {"valid": True, "type": "upi", "value": query}
        
        # Check if it's an email (backup check)
        if "@" in query and validators.email(query):
            return {"valid": True, "type": "email", "value": query}
        
        # Check if it's an IP address
        try:
            ipaddress.ip_address(query)
            return {"valid": True, "type": "ip", "value": query}
        except ValueError:
            pass
        
        # Check if it's a domain
        if validators.domain(query):
            return {"valid": True, "type": "domain", "value": query}
        
        # Check if it's a URL
        if validators.url(query):
            return {"valid": True, "type": "url", "value": query}
        
        # If none of the above, treat as username (alphanumeric with some special chars)
        if re.match(r'^[a-zA-Z0-9._-]+$', query) and len(query) >= 3:
            return {"valid": True, "type": "username", "value": query}
        
        return {
            "valid": False, 
            "error": "Invalid input. Please provide a valid phone number, Aadhaar number, vehicle number, UPI ID, email, IP address, domain, URL, or username."
        }
    
    async def call_osint_api(self, query: str, query_type: str) -> Dict[str, Any]:
        """
        Call the StormX OSINT API with the provided query
        
        Args:
            query (str): The query to search for
            query_type (str): Type of query (phone, aadhaar, vehicle, upi, etc.)
            
        Returns:
            Dict containing API response or error
        """
        try:
            headers = {
                'User-Agent': 'OSINT-Telegram-Bot/1.0',
                'Accept': 'application/json, text/html, */*'
            }
            
            # Map query types to API parameters
            params = {'key': self.api_key}
            
            if query_type == 'phone':
                params['number'] = query
            elif query_type == 'vehicle':
                params['vehicle'] = query
            elif query_type == 'aadhaar':
                params['aadhaar'] = query
            elif query_type == 'upi':
                params['upi'] = query
            else:
                # For other types not supported by StormX API
                return {"success": False, "error": f"Query type '{query_type}' is not supported by the current OSINT API"}
            
            # Make API request with enhanced error handling and retry logic
            logger.info(f"Making API request to: {self.api_base_url}")
            logger.info(f"Request parameters: {params}")
            
            max_retries = 3
            retry_delay = 1
            
            for attempt in range(max_retries):
                try:
                    response = self.session.get(
                        self.api_base_url,
                        headers=headers,
                        params=params,
                        timeout=30
                    )
                    
                    logger.info(f"API response status: {response.status_code} (attempt {attempt + 1})")
                    
                    if response.status_code == 200:
                        try:
                            json_data = response.json()
                            logger.info(f"Parsed JSON data: {json_data}")
                            return {"success": True, "data": json_data}
                        except Exception as e:
                            logger.error(f"Failed to parse JSON response: {e}")
                            # Return the raw text if JSON parsing fails
                            return {"success": True, "data": {"raw_response": response.text}}
                    elif response.status_code == 404:
                        logger.warning(f"API returned 404 - endpoint may be unavailable: {self.api_base_url}")
                        return {"success": False, "error": "OSINT API service is currently unavailable. The endpoint may be down or moved. Please contact the administrator."}
                    elif response.status_code == 401:
                        return {"success": False, "error": "API authentication failed - invalid API key"}
                    elif response.status_code == 429:
                        if attempt < max_retries - 1:
                            logger.warning(f"Rate limit hit, retrying in {retry_delay * (attempt + 1)} seconds")
                            time.sleep(retry_delay * (attempt + 1))
                            continue
                        return {"success": False, "error": "API rate limit exceeded. Please try again later"}
                    elif response.status_code >= 500:
                        if attempt < max_retries - 1:
                            logger.warning(f"Server error {response.status_code}, retrying in {retry_delay} seconds")
                            time.sleep(retry_delay)
                            continue
                        return {"success": False, "error": f"API server error (Status {response.status_code}). Please try again later."}
                    else:
                        logger.error(f"API returned unexpected status {response.status_code}: {response.text}")
                        return {"success": False, "error": f"API service error (Status {response.status_code}). Please try again later or contact the administrator."}
                
                except requests.exceptions.ConnectTimeout:
                    if attempt < max_retries - 1:
                        logger.warning(f"Connection timeout, retrying in {retry_delay} seconds")
                        time.sleep(retry_delay)
                        continue
                    logger.error("Connection timeout after all retries")
                    return {"success": False, "error": "Connection timeout. The OSINT API service may be down. Please try again later."}
                
                except requests.exceptions.ReadTimeout:
                    if attempt < max_retries - 1:
                        logger.warning(f"Read timeout, retrying in {retry_delay} seconds")
                        time.sleep(retry_delay)
                        continue
                    logger.error("Read timeout after all retries")
                    return {"success": False, "error": "Request timeout. Please try again later."}
                
                except requests.exceptions.ConnectionError as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Connection error: {e}, retrying in {retry_delay} seconds")
                        time.sleep(retry_delay)
                        continue
                    logger.error(f"Connection error after all retries: {e}")
                    return {"success": False, "error": "Unable to connect to OSINT API service. Please check your internet connection and try again later."}
                
                except Exception as e:
                    logger.error(f"Unexpected error during API request (attempt {attempt + 1}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    return {"success": False, "error": "An unexpected error occurred while processing your request. Please try again later."}
                    
        except requests.exceptions.Timeout:
            return {"success": False, "error": "API request timed out. Please try again"}
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": "Failed to connect to OSINT API"}
        except requests.exceptions.RequestException as e:
            logger.error(f"API request error: {e}")
            return {"success": False, "error": "An error occurred while calling the API"}
        except Exception as e:
            logger.error(f"Unexpected error in API call: {e}")
            return {"success": False, "error": "An unexpected error occurred"}
    
    def format_osint_response(self, query: str, data: Dict[str, Any], query_type: str) -> str:
        """
        Format the StormX OSINT API response into a readable message
        
        Args:
            query (str): The original query
            data (Dict): API response data
            query_type (str): Type of the query performed
            
        Returns:
            Formatted string message
        """
        if query_type == 'phone':
            icon = "�"
        elif query_type == 'vehicle':
            icon = "🚗"
        elif query_type == 'aadhaar':
            icon = "🆔"
        elif query_type == 'upi':
            icon = "💳"
        else:
            icon = "🔍"
            
        message = f"{icon} **OSINT Results for:** `{query}`\n"
        message += f"📊 **Query Type:** {query_type.upper()}\n\n"
        
        try:
            if isinstance(data, dict):
                # Check if response has 'data' array (StormX API format)
                if 'data' in data and data['data']:
                    data_array = data['data']
                    
                    if len(data_array) > 0:
                        for i, record in enumerate(data_array, 1):
                            if len(data_array) > 1:
                                message += f"**🔍 Record {i}:**\n"
                            
                            # Field mappings for StormX API response
                            field_mappings = {
                                'name': '👤 **Name**',
                                'fname': '� **Full Name**',
                                'mobile': '� **Mobile**',
                                'phone': '📱 **Phone**',
                                'address': '🏠 **Address**',
                                'circle': '📡 **Circle**',
                                'id': '🆔 **ID**',
                                'email': '📧 **Email**',
                                'location': '📍 **Location**',
                                'state': '🏛️ **State**',
                                'city': '🏙️ **City**',
                                'pincode': '📮 **Pincode**',
                                'owner': '👤 **Owner**',
                                'vehicle_number': '🚗 **Vehicle Number**',
                                'vehicle_type': '🚙 **Vehicle Type**',
                                'registration_date': '📅 **Registration Date**',
                                'bank': '🏦 **Bank**',
                                'account_type': '💳 **Account Type**',
                                'branch': '🏢 **Branch**',
                                'ifsc': '🔢 **IFSC Code**',
                                'age': '🎂 **Age**',
                                'gender': '⚧️ **Gender**',
                                'dob': '🎂 **Date of Birth**',
                                'father_name': '👨 **Father Name**',
                                'mother_name': '👩 **Mother Name**',
                                'status': '✅ **Status**',
                                'registered': '📝 **Registered**',
                                'verified': '✅ **Verified**',
                                'active': '🟢 **Active**'
                            }
                            
                            # Add formatted fields for this record
                            for key, value in record.items():
                                if value and str(value).strip():
                                    if key in field_mappings:
                                        message += f"{field_mappings[key]}: {value}\n"
                                    else:
                                        # Format unknown fields
                                        formatted_key = key.replace('_', ' ').title()
                                        message += f"**{formatted_key}:** {value}\n"
                            
                            if i < len(data_array):
                                message += "\n"
                    else:
                        message += "❌ **No data found for this query**\n"
                
                # Handle cases where there's a message field but no data
                elif 'message' in data:
                    message += f"ℹ️ **{data['message']}**\n"
                
                # Handle general fields that might be present (fallback)
                else:
                    field_mappings = {
                        'name': '👤 **Name**',
                        'phone': '📱 **Phone**',
                        'email': '📧 **Email**',
                        'address': '🏠 **Address**',
                        'location': '📍 **Location**',
                        'state': '🏛️ **State**',
                        'city': '🏙️ **City**',
                        'pincode': '📮 **Pincode**',
                        'owner': '👤 **Owner**',
                        'vehicle_number': '🚗 **Vehicle Number**',
                        'vehicle_type': '🚙 **Vehicle Type**',
                        'registration_date': '📅 **Registration Date**',
                        'bank': '🏦 **Bank**',
                        'account_type': '💳 **Account Type**',
                        'branch': '🏢 **Branch**',
                        'ifsc': '🔢 **IFSC Code**',
                        'age': '🎂 **Age**',
                        'gender': '⚧️ **Gender**',
                        'dob': '🎂 **Date of Birth**',
                        'father_name': '👨 **Father Name**',
                        'mother_name': '👩 **Mother Name**',
                        'status': '✅ **Status**',
                        'registered': '📝 **Registered**',
                        'verified': '✅ **Verified**',
                        'active': '🟢 **Active**'
                    }
                    
                    # Add formatted fields
                    data_found = False
                    for key, value in data.items():
                        if value and str(value).strip():
                            data_found = True
                            if key in field_mappings:
                                message += f"{field_mappings[key]}: {value}\n"
                            else:
                                # Format unknown fields
                                formatted_key = key.replace('_', ' ').title()
                                message += f"**{formatted_key}:** {value}\n"
                    
                    # If no specific fields found, show raw data in a cleaner format
                    if not data_found:
                        message += "❌ **No data found for this query**\n"
                
            else:
                # If data is not a dict, show it as is
                message += f"**Data:** {data}\n"
            
            # Add footer
            message += f"\n🕐 **Queried:** {data.get('timestamp', 'Just now')}"
            
        except Exception as e:
            logger.error(f"Error formatting response: {e}")
            message += "**Raw API Response:**\n"
            message += f"```json\n{str(data)[:800]}...\n```"
        
        return message
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /start command"""
        user = update.effective_user
        
        # Add user to database if not exists
        self.subscription_manager.db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        # Check subscription status
        is_subscribed = self.subscription_manager.db.is_user_subscribed(user.id)
        
        if is_subscribed:
            # User has active subscription - show full welcome
            welcome_message = f"""
👋 Hello {user.mention_html()}!

Welcome to <b>OSINT Intelligence Bot</b> (@{self.bot_username})! 🕵️‍♂️

✅ <b>Your subscription is ACTIVE!</b>

🔍 <b>Available Commands:</b>

📱 <b>Phone Lookup:</b> <code>/phone 9177075666</code>
🚗 <b>Vehicle Info:</b> <code>/vehicle JK05F1806</code>
🆔 <b>Aadhaar Lookup:</b> <code>/aadhar 123456789012</code>
💳 <b>UPI ID Search:</b> <code>/upi user@paytm</code>
🔧 <b>General Search:</b> <code>/osint query</code>

📊 <b>Account Commands:</b>
<code>/status</code> - Check subscription status
<code>/help</code> - Detailed help guide

🚀 <b>Ready to use!</b> Choose any command above to start your OSINT investigations.
            """
        else:
            # User needs subscription
            welcome_message = f"""
👋 Hello {user.mention_html()}!

Welcome to <b>OSINT Intelligence Bot</b> (@{self.bot_username})! 🕵️‍♂️

🔒 <b>Subscription Required</b>

To access our powerful OSINT features, you need an active subscription:

💰 <b>Subscription Details:</b>
• <b>Price:</b> ₹399
• <b>Duration:</b> 21 days
• <b>Features:</b> Unlimited OSINT queries

📱 <b>What You'll Get:</b>
✅ Phone number lookups
✅ Vehicle information  
✅ Aadhaar details
✅ UPI ID searches
✅ 24/7 access for 21 days

� <b>How to Subscribe:</b>
1. Contact admin: @ded_xdk
2. Complete payment of ₹399
3. Get instant access!

<b>Commands:</b>
<code>/subscribe</code> - Get subscription info
<code>/status</code> - Check your status
<code>/help</code> - Help guide
            """
        
        await update.message.reply_text(welcome_message, parse_mode='HTML')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /help command"""
        help_message = f"""
🆘 **Help - OSINT Bot Commands (@{self.bot_username})**

**🔍 Available Commands:**

📱 **Phone Lookup:** `/phone <number>`
   • Example: `/phone 9177075666`
   • Format: 10-digit Indian mobile numbers
   • With or without +91 country code

🚗 **Vehicle Information:** `/vehicle <registration>`
   • Example: `/vehicle JK05F1806`  
   • Format: Indian vehicle registration (AA##A####)
   • Provides: Owner, model, registration details

🆔 **Aadhaar Lookup:** `/aadhar <number>`
   • Example: `/aadhar 123456789012`
   • Format: 12-digit Aadhaar number
   • Spaces and hyphens automatically removed

💳 **UPI ID Lookup:** `/upi <upi_id>`
   • Example: `/upi user@paytm`
   • Format: username@bank or phone@upi
   • Supports major UPI providers

🔧 **General Lookup:** `/osint <query>`
   • Example: `/osint 9876543210`
   • Auto-detects data type from input
   • Supports all above formats

**Basic Commands:**
• `/start` - Show welcome message and commands
• `/help` - Show this detailed help

**Usage Tips:**
✅ Commands work with or without spaces
✅ Input validation prevents invalid queries
✅ Results are formatted for easy reading
✅ Processing status shows search progress

**Privacy & Ethics:**
This bot is designed for legitimate security research, threat intelligence, and educational purposes. Please use responsibly and in accordance with applicable laws and regulations.

Need assistance? The bot will guide you through each command.
        """
        
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    async def osint_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /osint command"""
        # Check subscription first
        user = update.effective_user
        self.subscription_manager.db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        if not self.subscription_manager.db.is_user_subscribed(user.id):
            await self.subscription_manager.send_subscription_required_message(update)
            return
        """Handle the /osint command"""
        if not context.args:
            await update.message.reply_text(
                "❌ Please provide a query to search for.\n\n"
                "**Usage:** `/osint <email|ip|domain|username>`\n"
                "**Example:** `/osint example@email.com`",
                parse_mode='Markdown'
            )
            return
        
        query = ' '.join(context.args).strip()
        user = update.effective_user
        
        logger.info(f"OSINT query from user {user.id} ({user.username}): {query}")
        
        # Send "typing" action to show bot is working
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        # Validate input
        validation_result = self.validate_input(query)
        
        if not validation_result["valid"]:
            await update.message.reply_text(
                f"❌ **Error:** {validation_result['error']}\n\n"
                "**Supported formats:**\n"
                "• Phone: 9876543210 (10 digits)\n"
                "• Vehicle: JK05F1806 (Indian format)\n"
                "• Aadhaar: 123456789012 (12 digits)\n"
                "• UPI: username@paytm\n"
                "• Email: user@domain.com (limited)\n"
                "• IP: 192.168.1.1 (limited)\n"
                "• Domain: example.com (limited)",
                parse_mode='Markdown'
            )
            return
        
        query_type = validation_result["type"]
        query_value = validation_result["value"]
        
        # Show processing message
        processing_msg = await update.message.reply_text(
            f"🔍 Searching OSINT databases for `{query_value}`...\n"
            f"📊 Query type: **{query_type.upper()}**",
            parse_mode='Markdown'
        )
        
        # Call OSINT API
        api_result = await self.call_osint_api(query_value, query_type)
        
        # Delete processing message
        await processing_msg.delete()
        
        if api_result["success"]:
            # Format and send successful response
            formatted_response = self.format_osint_response(query_value, api_result["data"], query_type)
            await update.message.reply_text(formatted_response, parse_mode='Markdown')
        else:
            # Send error message
            await update.message.reply_text(
                f"❌ **Error:** {api_result['error']}\n\n"
                "Please try again later or contact the administrator if the problem persists.",
                parse_mode='Markdown'
            )
    
    async def unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle unknown commands"""
        await update.message.reply_text(
            "❓ Unknown command. Use `/help` to see available commands.",
            parse_mode='Markdown'
        )
    
    async def phone_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /phone command for phone number lookup"""
        # Check subscription first
        user = update.effective_user
        self.subscription_manager.db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        if not self.subscription_manager.db.is_user_subscribed(user.id):
            await self.subscription_manager.send_subscription_required_message(update)
            return
        """Handle the /phone command for phone number lookup"""
        if not context.args:
            await update.message.reply_text(
                "📱 **Phone Number Lookup**\n\n"
                "Please provide a phone number to search.\n\n"
                "**Usage:** `/phone <number>`\n"
                "**Example:** `/phone 9177075666`\n\n"
                "**Supported formats:**\n"
                "• Indian mobile numbers (10 digits)\n"
                "• With or without +91 country code",
                parse_mode='Markdown'
            )
            return
        
        query = ' '.join(context.args)
        await self._process_osint_query(update, query, 'phone')
    
    async def vehicle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /vehicle command for vehicle lookup"""
        # Check subscription first
        user = update.effective_user
        self.subscription_manager.db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        if not self.subscription_manager.db.is_user_subscribed(user.id):
            await self.subscription_manager.send_subscription_required_message(update)
            return
        """Handle the /vehicle command for vehicle lookup"""
        if not context.args:
            await update.message.reply_text(
                "🚗 **Vehicle Information Lookup**\n\n"
                "Please provide a vehicle registration number to search.\n\n"
                "**Usage:** `/vehicle <registration_number>`\n"
                "**Example:** `/vehicle JK05F1806`\n\n"
                "**Supported formats:**\n"
                "• Indian vehicle registration numbers\n"
                "• Format: AA##A#### (State + District + Series + Number)",
                parse_mode='Markdown'
            )
            return
        
        query = ' '.join(context.args)
        await self._process_osint_query(update, query, 'vehicle')
    
    async def aadhar_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /aadhar command for Aadhaar lookup"""
        # Check subscription first
        user = update.effective_user
        self.subscription_manager.db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        if not self.subscription_manager.db.is_user_subscribed(user.id):
            await self.subscription_manager.send_subscription_required_message(update)
            return
        """Handle the /aadhar command for Aadhaar lookup"""
        if not context.args:
            await update.message.reply_text(
                "🆔 **Aadhaar Information Lookup**\n\n"
                "Please provide an Aadhaar number to search.\n\n"
                "**Usage:** `/aadhar <aadhaar_number>`\n"
                "**Example:** `/aadhar 123456789012`\n\n"
                "**Note:**\n"
                "• Aadhaar number should be 12 digits\n"
                "• Spaces and hyphens will be removed automatically",
                parse_mode='Markdown'
            )
            return
        
        query = ' '.join(context.args)
        await self._process_osint_query(update, query, 'aadhaar')
    
    async def upi_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /upi command for UPI ID lookup"""
        # Check subscription first
        user = update.effective_user
        self.subscription_manager.db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        if not self.subscription_manager.db.is_user_subscribed(user.id):
            await self.subscription_manager.send_subscription_required_message(update)
            return
        """Handle the /upi command for UPI ID lookup"""
        if not context.args:
            await update.message.reply_text(
                "💳 **UPI ID Lookup**\n\n"
                "Please provide a UPI ID to search.\n\n"
                "**Usage:** `/upi <upi_id>`\n"
                "**Example:** `/upi user@paytm`\n\n"
                "**Supported formats:**\n"
                "• username@bank (e.g., user@paytm)\n"
                "• phone@upi (e.g., 9876543210@ybl)",
                parse_mode='Markdown'
            )
            return
        
        query = ' '.join(context.args)
        await self._process_osint_query(update, query, 'upi')
    
    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /subscribe command - show subscription info and admin contact"""
        await self.subscription_manager.send_subscription_required_message(update)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /status command - show user's subscription status"""
        await self.subscription_manager.send_subscription_status(update)
    
    async def grant_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /grant command - admin only"""
        user = update.effective_user
        
        # Check if user is admin
        if not self.subscription_manager.is_admin(user.id):
            await update.message.reply_text(
                "❌ **Access Denied**\n\nThis command is for administrators only.",
                parse_mode='Markdown'
            )
            return
        
        # Check arguments
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "**Usage:** `/grant <user_id> [payment_reference]`\n\n"
                "**Example:**\n"
                "`/grant 123456789` - Grant subscription\n"
                "`/grant 123456789 PAY123` - Grant with payment reference",
                parse_mode='Markdown'
            )
            return
        
        try:
            target_user_id = int(context.args[0])
            payment_ref = context.args[1] if len(context.args) > 1 else f"ADMIN_GRANT_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Grant subscription
            success = await self.subscription_manager.grant_user_subscription(
                user_id=target_user_id,
                admin_id=user.id,
                payment_ref=payment_ref
            )
            
            if success:
                await update.message.reply_text(
                    f"✅ **Subscription Granted**\n\n"
                    f"**User ID:** {target_user_id}\n"
                    f"**Duration:** 21 days\n"
                    f"**Amount:** ₹399\n"
                    f"**Reference:** {payment_ref}\n"
                    f"**Granted by:** {user.first_name} ({user.id})",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"❌ **Failed to grant subscription**\n\n"
                    f"User {target_user_id} may not exist in the database.\n"
                    "Ask the user to try any command first to register.",
                    parse_mode='Markdown'
                )
                
        except ValueError:
            await update.message.reply_text(
                "❌ **Invalid user ID**\n\nPlease provide a valid numeric user ID.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error in grant command: {e}")
            await update.message.reply_text(
                "❌ **Error granting subscription**\n\nPlease try again later.",
                parse_mode='Markdown'
            )
    
    async def userinfo_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /userinfo command - admin only"""
        user = update.effective_user
        
        # Check if user is admin
        if not self.subscription_manager.is_admin(user.id):
            await update.message.reply_text(
                "❌ **Access Denied**\n\nThis command is for administrators only.",
                parse_mode='Markdown'
            )
            return
        
        if not context.args:
            await update.message.reply_text(
                "**Usage:** `/userinfo <user_id>`\n\n"
                "**Example:** `/userinfo 123456789`",
                parse_mode='Markdown'
            )
            return
        
        try:
            target_user_id = int(context.args[0])
            stats = self.subscription_manager.db.get_user_stats(target_user_id)
            user_data = self.subscription_manager.db.get_user(target_user_id)
            
            if not stats or not user_data:
                await update.message.reply_text(
                    f"❌ **User not found**\n\nUser {target_user_id} is not in the database.",
                    parse_mode='Markdown'
                )
                return
            
            message = f"""
📋 **User Information**

**👤 User Details:**
• **ID:** {user_data['user_id']}
• **Username:** @{user_data['username'] or 'N/A'}
• **Name:** {user_data['first_name']} {user_data['last_name'] or ''}
• **Joined:** {user_data['created_at'][:10]}

**💳 Subscription:**
• **Status:** {stats['subscription_status'].title()}
• **Start:** {stats['subscription_start'][:10] if stats['subscription_start'] else 'N/A'}
• **End:** {stats['subscription_end'][:10] if stats['subscription_end'] else 'N/A'}
• **Days Left:** {stats['days_remaining']}
• **Amount Paid:** ₹{stats['payment_amount'] or 0}

**📊 Usage:**
• **Queries Used:** {stats['queries_used']}
• **Payment Ref:** {user_data['payment_reference'] or 'N/A'}
            """
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except ValueError:
            await update.message.reply_text(
                "❌ **Invalid user ID**\n\nPlease provide a valid numeric user ID.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error in userinfo command: {e}")
            await update.message.reply_text(
                "❌ **Error getting user info**\n\nPlease try again later.",
                parse_mode='Markdown'
            )
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /admin command - show admin help"""
        user = update.effective_user
        
        # Check if user is admin
        if not self.subscription_manager.is_admin(user.id):
            await update.message.reply_text(
                "❌ **Access Denied**\n\nThis command is for administrators only.",
                parse_mode='Markdown'
            )
            return
        
        await self.subscription_manager.send_admin_help(update)
    
    async def callback_query_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback queries from inline keyboards"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "check_status":
            # Replace the message with status info
            user = query.from_user
            stats = self.subscription_manager.db.get_user_stats(user.id)
            
            if not stats:
                text = "❌ User not found in database. Try using any command first."
            else:
                status = stats.get('subscription_status', 'inactive')
                if status == 'active':
                    text = f"✅ <b>Active Subscription</b>\n⏳ Days remaining: {stats.get('days_remaining', 0)}"
                else:
                    text = f"🔒 <b>No active subscription</b>\nContact @ded_xdk to subscribe"
            
            await query.edit_message_text(text, parse_mode='HTML')

    async def _process_osint_query(self, update: Update, query: str, query_type: str) -> None:
        """
        Process OSINT query for specific command types
        
        Args:
            update: Telegram update object
            query: The search query
            query_type: Type of OSINT query (phone, vehicle, aadhaar, upi)
        """
        user = update.effective_user
        logger.info(f"OSINT {query_type} query from user {user.id} ({user.username}): {query}")
        
        # Validate the input
        validation_result = self.validate_input(query)
        
        if not validation_result["valid"]:
            await update.message.reply_text(
                f"❌ **Invalid {query_type} format:**\n{validation_result['error']}\n\n"
                f"Use `/help` for format examples.",
                parse_mode='Markdown'
            )
            return
        
        # Check if the detected type matches the command type
        detected_type = validation_result["type"]
        if detected_type != query_type:
            await update.message.reply_text(
                f"❌ **Query Type Mismatch:**\n"
                f"You used `/{query_type}` command but the input appears to be a {detected_type}.\n\n"
                f"Please use the correct command: `/{detected_type} {query}`",
                parse_mode='Markdown'
            )
            return
        
        query_value = validation_result["value"]
        
        # Send processing message
        processing_msg = await update.message.reply_text(
            f"🔍 **Processing {query_type} lookup...**\n"
            "Please wait while I search the databases.",
            parse_mode='Markdown'
        )
        
        # Send typing action
        await update.message.chat.send_action(action="typing")
        
        # Call OSINT API
        api_result = await self.call_osint_api(query_value, query_type)
        
        # Delete processing message
        await processing_msg.delete()
        
        if api_result["success"]:
            # Format and send successful response
            formatted_response = self.format_osint_response(query_value, api_result["data"], query_type)
            await update.message.reply_text(formatted_response, parse_mode='Markdown')
        else:
            # Send error message
            await update.message.reply_text(
                f"❌ **Error:** {api_result['error']}\n\n"
                "Please try again later or contact the administrator if the problem persists.",
                parse_mode='Markdown'
            )
    
    def run(self):
        """Start the bot with health monitoring"""
        try:
            # Create the Application
            application = Application.builder().token(self.bot_token).build()
            
            # Add command handlers
            application.add_handler(CommandHandler("start", self.start_command))
            application.add_handler(CommandHandler("help", self.help_command))
            application.add_handler(CommandHandler("osint", self.osint_command))
            
            # Add specialized OSINT command handlers
            application.add_handler(CommandHandler("phone", self.phone_command))
            application.add_handler(CommandHandler("vehicle", self.vehicle_command))
            application.add_handler(CommandHandler("aadhar", self.aadhar_command))
            application.add_handler(CommandHandler("upi", self.upi_command))
            
            # Add subscription command handlers
            application.add_handler(CommandHandler("subscribe", self.subscribe_command))
            application.add_handler(CommandHandler("status", self.status_command))
            
            # Add admin command handlers
            application.add_handler(CommandHandler("grant", self.grant_command))
            application.add_handler(CommandHandler("userinfo", self.userinfo_command))
            application.add_handler(CommandHandler("admin", self.admin_command))
            
            # Add callback query handler for inline keyboards
            application.add_handler(CallbackQueryHandler(self.callback_query_handler))
            
            # Add handler for unknown commands
            application.add_handler(MessageHandler(filters.COMMAND, self.unknown_command))
            
            # Add error handler
            application.add_error_handler(self.error_handler)
            
            logger.info("Starting OSINT Bot...")
            
            # Run the bot until the user presses Ctrl-C
            application.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            raise


def main():
    """Main function to run the bot"""
    try:
        bot = OSINTBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise


if __name__ == '__main__':
    main()