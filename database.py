"""
Supabase Database module for OSINT Bot subscription system
Uses Supabase for cloud database storage with shared access between both bots
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from supabase import create_client, Client

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Database manager for OSINT Bot user subscriptions using Supabase"""
    
    def __init__(self, supabase_url: str = None, supabase_key: str = None):
        self.supabase_url = supabase_url or os.getenv('SUPABASE_URL')
        self.supabase_key = supabase_key or os.getenv('SUPABASE_KEY')
        
        if not self.supabase_url or not self.supabase_key:
            # Fallback to local SQLite for development
            logger.warning("Supabase credentials not found, falling back to SQLite")
            self.use_sqlite = True
            self._init_sqlite()
        else:
            self.use_sqlite = False
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
            self.init_database()
    
    def _init_sqlite(self):
        """Initialize SQLite for local development"""
        import sqlite3
        self.db_path = "../osint_bot.db"
        self._create_sqlite_tables()
    
    def _create_sqlite_tables(self):
        """Create SQLite tables for local development"""
        import sqlite3
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    subscription_status TEXT DEFAULT 'inactive',
                    subscription_start_date TEXT,
                    subscription_end_date TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount REAL,
                    currency TEXT,
                    payment_method TEXT,
                    transaction_id TEXT,
                    status TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usage_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    endpoint TEXT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    success BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            conn.commit()
            conn.close()
            logger.info("SQLite database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing SQLite database: {e}")
            raise
    
    def init_database(self):
        """Initialize Supabase database tables"""
        if self.use_sqlite:
            return
            
        try:
            # Check if tables exist, if not they should be created via Supabase dashboard
            # This is just a connection test
            result = self.supabase.table('users').select("count", count='exact').execute()
            logger.info(f"Supabase database connected successfully. Users table has {result.count} records")
        except Exception as e:
            logger.error(f"Error connecting to Supabase: {e}")
            raise
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> bool:
        """Add a new user to the database"""
        try:
            if self.use_sqlite:
                return self._add_user_sqlite(user_id, username, first_name, last_name)
            
            user_data = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
                'updated_at': datetime.now().isoformat()
            }
            
            # Try to insert, if conflict then update
            result = self.supabase.table('users').upsert(user_data).execute()
            logger.info(f"User {user_id} added/updated successfully in Supabase")
            return True
        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")
            return False
    
    def _add_user_sqlite(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> bool:
        """Add user to SQLite (fallback)"""
        import sqlite3
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, updated_at) 
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, first_name, last_name, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            logger.info(f"User {user_id} added/updated successfully in SQLite")
            return True
        except Exception as e:
            logger.error(f"Error adding user {user_id} to SQLite: {e}")
            return False
    
    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user information"""
        try:
            if self.use_sqlite:
                return self._get_user_sqlite(user_id)
            
            result = self.supabase.table('users').select("*").eq('user_id', user_id).execute()
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None
    
    def _get_user_sqlite(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user from SQLite (fallback)"""
        import sqlite3
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, username, first_name, last_name, subscription_status,
                       subscription_start_date, subscription_end_date, created_at, updated_at
                FROM users WHERE user_id = ?
            """, (user_id,))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting user {user_id} from SQLite: {e}")
            return None
    
    def update_subscription(self, user_id: int, status: str, days: int = 30) -> bool:
        """Update user subscription status"""
        try:
            if self.use_sqlite:
                return self._update_subscription_sqlite(user_id, status, days)
            
            update_data = {
                'subscription_status': status,
                'updated_at': datetime.now().isoformat()
            }
            
            if status == 'active':
                start_date = datetime.now()
                end_date = start_date + timedelta(days=days)
                update_data['subscription_start_date'] = start_date.isoformat()
                update_data['subscription_end_date'] = end_date.isoformat()
            
            result = self.supabase.table('users').update(update_data).eq('user_id', user_id).execute()
            logger.info(f"Subscription updated for user {user_id}: {status}")
            return True
        except Exception as e:
            logger.error(f"Error updating subscription for user {user_id}: {e}")
            return False
    
    def _update_subscription_sqlite(self, user_id: int, status: str, days: int = 30) -> bool:
        """Update subscription in SQLite (fallback)"""
        import sqlite3
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if status == 'active':
                start_date = datetime.now()
                end_date = start_date + timedelta(days=days)
                cursor.execute("""
                    UPDATE users 
                    SET subscription_status = ?, subscription_start_date = ?, subscription_end_date = ?, updated_at = ?
                    WHERE user_id = ?
                """, (status, start_date.isoformat(), end_date.isoformat(), datetime.now().isoformat(), user_id))
            else:
                cursor.execute("""
                    UPDATE users 
                    SET subscription_status = ?, updated_at = ?
                    WHERE user_id = ?
                """, (status, datetime.now().isoformat(), user_id))
            
            conn.commit()
            conn.close()
            logger.info(f"Subscription updated for user {user_id}: {status}")
            return True
        except Exception as e:
            logger.error(f"Error updating subscription for user {user_id} in SQLite: {e}")
            return False
    
    def is_user_active(self, user_id: int) -> bool:
        """Check if user has active subscription"""
        user = self.get_user(user_id)
        if not user or user['subscription_status'] != 'active':
            return False
        
        if user['subscription_end_date']:
            if isinstance(user['subscription_end_date'], str):
                end_date = datetime.fromisoformat(user['subscription_end_date'].replace('Z', '+00:00'))
            else:
                end_date = user['subscription_end_date']
            return datetime.now() < end_date.replace(tzinfo=None)
        return False
    
    def is_user_subscribed(self, user_id: int) -> bool:
        """Check if user has active subscription (alias for is_user_active)"""
        return self.is_user_active(user_id)
    
    def get_all_users(self) -> list:
        """Get all users"""
        try:
            if self.use_sqlite:
                return self._get_all_users_sqlite()
            
            result = self.supabase.table('users').select("*").order('created_at', desc=True).execute()
            return result.data
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []
    
    def _get_all_users_sqlite(self) -> list:
        """Get all users from SQLite (fallback)"""
        import sqlite3
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, username, first_name, last_name, subscription_status,
                       subscription_start_date, subscription_end_date, created_at
                FROM users ORDER BY created_at DESC
            """)
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting all users from SQLite: {e}")
            return []
    
    def get_all_active_users(self) -> list:
        """Get all active users with enhanced information"""
        try:
            if self.use_sqlite:
                return self._get_all_active_users_sqlite()
            
            result = self.supabase.table('users').select("*").eq('subscription_status', 'active').order('created_at', desc=True).execute()
            
            # Filter by subscription end date
            active_users = []
            for user in result.data:
                if user['subscription_end_date']:
                    if isinstance(user['subscription_end_date'], str):
                        end_date = datetime.fromisoformat(user['subscription_end_date'].replace('Z', '+00:00'))
                    else:
                        end_date = user['subscription_end_date']
                    if datetime.now() < end_date.replace(tzinfo=None):
                        active_users.append(user)
                else:
                    active_users.append(user)
            
            return active_users
        except Exception as e:
            logger.error(f"Error getting active users: {e}")
            return []
    
    def _get_all_active_users_sqlite(self) -> list:
        """Get all active users from SQLite (fallback)"""
        import sqlite3
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, username, first_name, last_name, subscription_status,
                       subscription_start_date, subscription_end_date, created_at
                FROM users 
                WHERE subscription_status = 'active' 
                AND (subscription_end_date IS NULL OR subscription_end_date > ?)
                ORDER BY created_at DESC
            """, (datetime.now().isoformat(),))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting active users from SQLite: {e}")
            return []
    
    def log_usage(self, user_id: int, endpoint: str, success: bool = True) -> bool:
        """Log API usage"""
        try:
            if self.use_sqlite:
                return self._log_usage_sqlite(user_id, endpoint, success)
            
            log_data = {
                'user_id': user_id,
                'endpoint': endpoint,
                'success': success,
                'timestamp': datetime.now().isoformat()
            }
            
            result = self.supabase.table('usage_logs').insert(log_data).execute()
            return True
        except Exception as e:
            logger.error(f"Error logging usage for user {user_id}: {e}")
            return False
    
    def _log_usage_sqlite(self, user_id: int, endpoint: str, success: bool = True) -> bool:
        """Log usage in SQLite (fallback)"""
        import sqlite3
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO usage_logs (user_id, endpoint, success, timestamp)
                VALUES (?, ?, ?, ?)
            """, (user_id, endpoint, success, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error logging usage for user {user_id} in SQLite: {e}")
            return False