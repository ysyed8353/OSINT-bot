"""
Subscription Manager for OSINT Bot
Handles subscription validation, user management, and payment processing
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import DatabaseManager

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """Manages user subscriptions and access control"""
    
    def __init__(self, admin_username: str = "ded_xdk", admin_id: int = None):
        self.db = DatabaseManager()
        self.admin_username = admin_username
        self.admin_id = admin_id
        self.subscription_price = 399.0
        self.subscription_days = 21
    
    def require_subscription(self, func: Callable) -> Callable:
        """Decorator to check if user has active subscription before executing command"""
        @wraps(func)
        async def wrapper(bot_instance, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user = update.effective_user
            
            # Add user to database if not exists
            self.db.add_user(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            
            # Check subscription status
            if not self.db.is_user_subscribed(user.id):
                await self.send_subscription_required_message(update)
                return
            
            # Log usage
            command_name = func.__name__.replace('_command', '')
            query = ' '.join(context.args) if context.args else 'N/A'
            self.db.log_usage(user.id, command_name, query)
            
            # Execute the original function
            return await func(bot_instance, update, context, *args, **kwargs)
        
        return wrapper
    
    async def send_subscription_required_message(self, update: Update):
        """Send subscription required message with admin contact"""
        user = update.effective_user
        user_stats = self.db.get_user_stats(user.id)
        
        if user_stats.get('subscription_status') == 'expired':
            status_text = "⏰ **Your subscription has expired!**"
        else:
            status_text = "🔒 **Subscription Required**"
        
        message = f"""
{status_text}

Hello {user.first_name}! 👋

To use the OSINT Intelligence Bot, you need an active subscription.

💰 <b>Subscription Details:</b>
• <b>Price:</b> ₹{self.subscription_price}
• <b>Duration:</b> {self.subscription_days} days
• <b>Features:</b> Unlimited OSINT queries

📞 <b>How to Subscribe:</b>
1. Contact our admin: @{self.admin_username}
2. Complete payment of ₹{self.subscription_price}
3. Get instant access for {self.subscription_days} days!

🔐 <b>What you'll get:</b>
✅ Phone number lookups
✅ Vehicle information
✅ Aadhaar details
✅ UPI ID searches
✅ 24/7 access for {self.subscription_days} days

Click the button below to contact admin:
        """
        
        # Create inline keyboard with admin contact
        keyboard = [
            [InlineKeyboardButton(f"📞 Contact Admin @{self.admin_username}", 
                                url=f"https://t.me/{self.admin_username}")],
            [InlineKeyboardButton("📊 Check Status", callback_data="check_status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
    
    async def send_subscription_status(self, update: Update):
        """Send user's current subscription status"""
        user = update.effective_user
        stats = self.db.get_user_stats(user.id)
        
        if not stats:
            await update.message.reply_text(
                "❌ <b>User not found in database.</b>\n"
                "Please try using any command first to register.",
                parse_mode='HTML'
            )
            return
        
        status = stats.get('subscription_status', 'inactive')
        
        if status == 'active':
            message = f"""
✅ **Active Subscription**

👤 **User:** {user.first_name} (@{user.username or 'N/A'})
💳 **Status:** Active
📅 **Started:** {stats.get('subscription_start', 'N/A')[:10] if stats.get('subscription_start') else 'N/A'}
⏰ **Expires:** {stats.get('subscription_end', 'N/A')[:10] if stats.get('subscription_end') else 'N/A'}
⏳ **Days Remaining:** {stats.get('days_remaining', 0)}
🔍 **Queries Used:** {stats.get('queries_used', 0)}
💰 **Amount Paid:** ₹{stats.get('payment_amount', 0)}

🎉 **Your subscription is active!** 
You can use all OSINT features until expiry.
            """
        elif status == 'expired':
            message = f"""
⏰ **Subscription Expired**

👤 **User:** {user.first_name} (@{user.username or 'N/A'})
💳 **Status:** Expired
📅 **Expired on:** {stats.get('subscription_end', 'N/A')[:10] if stats.get('subscription_end') else 'N/A'}
🔍 **Total Queries Used:** {stats.get('queries_used', 0)}

To renew your subscription:
📞 Contact admin: @{self.admin_username}
💰 Price: ₹{self.subscription_price} for {self.subscription_days} days
            """
        else:
            message = f"""
🔒 **No Active Subscription**

👤 **User:** {user.first_name} (@{user.username or 'N/A'})
💳 **Status:** Inactive
🔍 **Queries Used:** {stats.get('queries_used', 0)}

To get subscription:
📞 Contact admin: @{self.admin_username}
💰 Price: ₹{self.subscription_price} for {self.subscription_days} days
            """
        
        # Add contact admin button for inactive/expired users
        if status != 'active':
            keyboard = [[InlineKeyboardButton(f"📞 Contact Admin @{self.admin_username}", 
                                            url=f"https://t.me/{self.admin_username}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
        else:
            reply_markup = None
        
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return self.admin_id and user_id == self.admin_id
    
    async def grant_user_subscription(self, user_id: int, admin_id: int, payment_ref: str = None) -> bool:
        """Grant subscription to a user (admin function)"""
        try:
            # Ensure user exists in database
            user_data = self.db.get_user(user_id)
            if not user_data:
                return False
            
            # Grant subscription
            success = self.db.grant_subscription(
                user_id=user_id,
                days=self.subscription_days,
                amount=self.subscription_price,
                admin_id=admin_id,
                payment_ref=payment_ref
            )
            
            if success:
                logger.info(f"Admin {admin_id} granted subscription to user {user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error granting subscription: {e}")
            return False
    
    async def send_admin_help(self, update: Update):
        """Send admin command help"""
        message = f"""
🔧 **Admin Commands**

**User Management:**
`/grant <user_id> [payment_ref]` - Grant {self.subscription_days} days subscription
`/revoke <user_id>` - Revoke user subscription
`/userinfo <user_id>` - Get user details
`/stats` - Get bot statistics

**Examples:**
`/grant 123456789` - Grant subscription to user
`/grant 123456789 PAY123` - Grant with payment reference
`/userinfo 123456789` - Get user subscription info

**Price:** ₹{self.subscription_price} for {self.subscription_days} days
**Admin:** @{self.admin_username}
        """
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def get_bot_statistics(self) -> Dict[str, Any]:
        """Get bot usage statistics"""
        try:
            active_users = self.db.get_all_active_users()
            
            stats = {
                'active_subscriptions': len(active_users),
                'total_users': len(self.db.get_all_active_users()),  # This would need a separate method
                'revenue': len(active_users) * self.subscription_price
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {}