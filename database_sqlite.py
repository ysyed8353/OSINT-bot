"""
Database module for OSINT Bot subscription system
Handles user management, subscription tracking, and payment verification
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import os

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Database manager for OSINT Bot user subscriptions"""
    
    def __init__(self, db_path: str = "../osint_bot.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database and create tables if they don't exist"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create users table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        subscription_status TEXT DEFAULT 'inactive',
                        subscription_start_date TEXT,
                        subscription_end_date TEXT,
                        payment_amount REAL,
                        payment_reference TEXT,
                        queries_used INTEGER DEFAULT 0,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create payment_logs table for tracking transactions
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS payment_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        amount REAL,
                        reference TEXT,
                        admin_id INTEGER,
                        granted_days INTEGER,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Create usage_logs table for tracking API usage
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS usage_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        command_type TEXT,
                        query TEXT,
                        success BOOLEAN,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                conn.commit()
                logger.info("Database initialized successfully")
                
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> bool:
        """Add a new user to the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if user already exists
                cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                if cursor.fetchone():
                    return True  # User already exists
                
                # Insert new user
                cursor.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name))
                
                conn.commit()
                logger.info(f"Added new user: {user_id} ({username})")
                return True
                
        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")
            return False
    
    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user information from database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None
    
    def grant_subscription(self, user_id: int, days: int = 21, amount: float = 399.0, 
                          admin_id: int = None, payment_ref: str = None) -> bool:
        """Grant subscription access to a user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Calculate subscription dates
                start_date = datetime.now()
                end_date = start_date + timedelta(days=days)
                
                # Update user subscription
                cursor.execute('''
                    UPDATE users 
                    SET subscription_status = 'active',
                        subscription_start_date = ?,
                        subscription_end_date = ?,
                        payment_amount = ?,
                        payment_reference = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (start_date.isoformat(), end_date.isoformat(), amount, payment_ref, user_id))
                
                # Log the payment
                cursor.execute('''
                    INSERT INTO payment_logs (user_id, amount, reference, admin_id, granted_days)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, amount, payment_ref, admin_id, days))
                
                conn.commit()
                logger.info(f"Granted {days} days subscription to user {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error granting subscription to user {user_id}: {e}")
            return False
    
    def is_user_subscribed(self, user_id: int) -> bool:
        """Check if user has an active subscription"""
        try:
            user = self.get_user(user_id)
            if not user:
                return False
            
            if user['subscription_status'] != 'active':
                return False
            
            if not user['subscription_end_date']:
                return False
            
            # Check if subscription has expired
            end_date = datetime.fromisoformat(user['subscription_end_date'])
            if datetime.now() > end_date:
                # Subscription expired, update status
                self.expire_subscription(user_id)
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking subscription for user {user_id}: {e}")
            return False
    
    def expire_subscription(self, user_id: int) -> bool:
        """Mark user subscription as expired"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE users 
                    SET subscription_status = 'expired',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (user_id,))
                
                conn.commit()
                logger.info(f"Expired subscription for user {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error expiring subscription for user {user_id}: {e}")
            return False
    
    def log_usage(self, user_id: int, command_type: str, query: str, success: bool = True) -> bool:
        """Log user command usage"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Log the usage
                cursor.execute('''
                    INSERT INTO usage_logs (user_id, command_type, query, success)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, command_type, query, success))
                
                # Update user query count
                cursor.execute('''
                    UPDATE users 
                    SET queries_used = queries_used + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (user_id,))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error logging usage for user {user_id}: {e}")
            return False
    
    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get user subscription and usage statistics"""
        try:
            user = self.get_user(user_id)
            if not user:
                return {}
            
            stats = {
                'user_id': user['user_id'],
                'subscription_status': user['subscription_status'],
                'queries_used': user['queries_used'],
                'subscription_start': user['subscription_start_date'],
                'subscription_end': user['subscription_end_date'],
                'payment_amount': user['payment_amount']
            }
            
            # Calculate days remaining
            if user['subscription_end_date']:
                end_date = datetime.fromisoformat(user['subscription_end_date'])
                days_remaining = (end_date - datetime.now()).days
                stats['days_remaining'] = max(0, days_remaining)
            else:
                stats['days_remaining'] = 0
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting stats for user {user_id}: {e}")
            return {}
    
    def get_all_active_users(self) -> list:
        """Get all users with active subscriptions"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT user_id, username, subscription_end_date, queries_used
                    FROM users 
                    WHERE subscription_status = 'active'
                    ORDER BY subscription_end_date DESC
                ''')
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"Error getting active users: {e}")
            return []