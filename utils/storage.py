"""
Persistent storage for multi-user wallets with Google Cloud KMS encryption.

Uses Google Cloud KMS for encryption - keys never stored locally.
All private keys are encrypted by Google's Hardware Security Modules (HSMs).

Database: PostgreSQL (Supabase) via psycopg2 direct connection

Schema (run supabase_schema.sql to add telegram_id column):
- id (BIGSERIAL) - auto-increment primary key
- telegram_id (TEXT UNIQUE) - Telegram user ID (stored as string)
- telegram_username (TEXT) - @username
- address (TEXT) - wallet address
- private_key (TEXT) - KMS-encrypted private key
- created_at (TIMESTAMPTZ)
"""

import os
import time
from typing import Optional, Dict, Any, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from utils.google_kms import KMSEncryption


# Default settings for new users
DEFAULT_SETTINGS = {
    "auto_reload": True,
    "confirm_trades": True,
    "show_pnl": True,
    "show_charts": True,
    "language": "en",
    "auto_reload_bnb": True,
    "bnb_threshold": 0.01,
    "bnb_reload_amount": 0.02,
    "default_bet": 50,
}


class UserStorage:
    """Encrypted storage for user wallets using PostgreSQL + Google Cloud KMS.

    Features:
    - Direct PostgreSQL connection via psycopg2 (no Supabase SDK)
    - In-memory cache for decrypted keys (5 minute TTL)
    - Rate-limited KMS calls
    - Automatic retry on transient failures
    """

    # Cache TTL in seconds (5 minutes)
    CACHE_TTL = 300

    def __init__(self, db_url: Optional[str] = None):
        """Initialize PostgreSQL storage with Google Cloud KMS encryption."""
        # PostgreSQL setup
        if db_url is None:
            db_url = os.getenv("DATABASE_URL")
            if not db_url:
                raise ValueError("DATABASE_URL not found in environment")

        self.db_url = db_url
        self.conn = psycopg2.connect(db_url)
        self.conn.autocommit = False  # Manual transaction control

        # Google Cloud KMS setup
        self.kms = KMSEncryption()
        print("✅ Using Google Cloud KMS for encryption")

        # In-memory cache for decrypted private keys: {telegram_id: (private_key, expiry_time)}
        self._key_cache: Dict[int, Tuple[str, float]] = {}

    def _ensure_connection(self):
        """Ensure database connection is alive, reconnect if needed."""
        try:
            # Test connection with a simple query
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            print(f"Database connection lost, reconnecting: {e}")
            try:
                self.conn = psycopg2.connect(self.db_url)
                self.conn.autocommit = False
                print("✅ Database reconnected successfully")
            except Exception as reconnect_error:
                print(f"❌ Failed to reconnect to database: {reconnect_error}")
                raise

    def _encrypt(self, data: str) -> str:
        """Encrypt sensitive data using Google Cloud KMS."""
        return self.kms.encrypt(data)

    def _decrypt(self, encrypted_data: str) -> str:
        """Decrypt sensitive data using Google Cloud KMS."""
        return self.kms.decrypt(encrypted_data)

    def save_wallet(self, telegram_id: int, wallet_address: str, private_key: str, telegram_username: Optional[str] = None) -> bool:
        """Save or update user's wallet."""
        encrypted_key = self._encrypt(private_key)
        telegram_id_str = str(telegram_id)

        # Clear cache for this user (wallet changed)
        if telegram_id in self._key_cache:
            del self._key_cache[telegram_id]

        try:
            with self.conn.cursor() as cur:
                # Upsert: insert or update if telegram_id already exists
                cur.execute("""
                    INSERT INTO wallets (telegram_id, telegram_username, address, private_key)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (telegram_id)
                    DO UPDATE SET
                        address = EXCLUDED.address,
                        private_key = EXCLUDED.private_key,
                        telegram_username = EXCLUDED.telegram_username
                """, (telegram_id_str, telegram_username, wallet_address, encrypted_key))
                self.conn.commit()
            return True
        except Exception as e:
            self.conn.rollback()
            print(f"Error saving wallet: {e}")
            return False

    def get_private_key(self, telegram_id: int) -> Optional[str]:
        """Get decrypted private key by telegram_id (with caching).

        Args:
            telegram_id: Telegram user ID

        Returns:
            Decrypted private key or None if not found

        Notes:
            - Cached for 5 minutes to reduce KMS calls
            - Cache is automatically cleared on wallet save/delete
        """
        # Check cache first
        if telegram_id in self._key_cache:
            cached_key, expiry_time = self._key_cache[telegram_id]
            if time.time() < expiry_time:
                return cached_key
            else:
                # Cache expired, remove it
                del self._key_cache[telegram_id]

        # Not in cache or expired - fetch from DB and decrypt
        telegram_id_str = str(telegram_id)

        try:
            # Ensure connection is alive
            self._ensure_connection()

            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT private_key FROM wallets WHERE telegram_id = %s",
                    (telegram_id_str,)
                )
                result = cur.fetchone()

            if not result:
                print(f"No wallet found in database for telegram_id: {telegram_id}")
                return None

            encrypted_key = result["private_key"]

            try:
                decrypted_key = self._decrypt(encrypted_key)
            except Exception as decrypt_error:
                print(f"KMS decryption failed for telegram_id {telegram_id}: {decrypt_error}")
                return None

            # Cache the decrypted key
            self._key_cache[telegram_id] = (decrypted_key, time.time() + self.CACHE_TTL)

            return decrypted_key
        except Exception as e:
            print(f"Error getting private key for telegram_id {telegram_id}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_wallet_address(self, telegram_id: int) -> Optional[str]:
        """Get wallet address by telegram_id."""
        telegram_id_str = str(telegram_id)

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT address FROM wallets WHERE telegram_id = %s",
                    (telegram_id_str,)
                )
                result = cur.fetchone()

            if not result:
                return None

            return result["address"]
        except Exception as e:
            print(f"Error getting wallet address: {e}")
            return None

    def has_wallet(self, telegram_id: int) -> bool:
        """Check if user has wallet."""
        telegram_id_str = str(telegram_id)

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM wallets WHERE telegram_id = %s LIMIT 1",
                    (telegram_id_str,)
                )
                result = cur.fetchone()
            return result is not None
        except Exception as e:
            print(f"Error checking wallet: {e}")
            return False

    def delete_wallet(self, telegram_id: int) -> bool:
        """Delete wallet."""
        telegram_id_str = str(telegram_id)

        # Clear cache for this user
        if telegram_id in self._key_cache:
            del self._key_cache[telegram_id]

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM wallets WHERE telegram_id = %s",
                    (telegram_id_str,)
                )
                self.conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            self.conn.rollback()
            print(f"Error deleting wallet: {e}")
            return False

    def save_settings(self, telegram_id: int, settings: Dict[str, Any]) -> bool:
        """Save user settings to database."""
        telegram_id_str = str(telegram_id)

        try:
            import json
            with self.conn.cursor() as cur:
                cur.execute("""
                    UPDATE wallets
                    SET settings = %s
                    WHERE telegram_id = %s
                """, (json.dumps(settings), telegram_id_str))
                self.conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            self.conn.rollback()
            print(f"Error saving settings: {e}")
            return False

    def get_settings(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get user settings from database, or return defaults if not found."""
        telegram_id_str = str(telegram_id)

        try:
            import json
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT settings FROM wallets WHERE telegram_id = %s
                """, (telegram_id_str,))
                result = cur.fetchone()

            if result and result['settings']:
                # Merge saved settings with defaults (in case new settings were added)
                merged = DEFAULT_SETTINGS.copy()
                merged.update(result['settings'])
                return merged
            else:
                return DEFAULT_SETTINGS.copy()
        except Exception as e:
            print(f"Error getting settings: {e}")
            return DEFAULT_SETTINGS.copy()

    def update_last_active(self, telegram_id: int) -> bool:
        """No last_active column."""
        return True

    def get_all_active_users(self) -> list[int]:
        """Get all telegram_ids."""
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT telegram_id FROM wallets")
                results = cur.fetchall()
            # Convert string telegram_ids back to integers
            return [int(row["telegram_id"]) for row in results if row.get("telegram_id")]
        except Exception as e:
            print(f"Error getting active users: {e}")
            return []


# Singleton instance
_storage_instance: Optional[UserStorage] = None


def get_storage() -> UserStorage:
    """Get the global storage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = UserStorage()
    return _storage_instance


def init_storage(db_url: Optional[str] = None):
    """Initialize the global storage instance."""
    global _storage_instance
    _storage_instance = UserStorage(db_url=db_url)
    return _storage_instance
