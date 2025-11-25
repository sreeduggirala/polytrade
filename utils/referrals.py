"""
Referral and Points System

Features:
- Auto-generated 7-character alphanumeric referral codes
- Customizable referral codes
- Points tracking based on volume (1 point per $1)
- Referral bonuses (100 points for signup, 10% of referred user's points)
"""

import random
import string
from typing import Optional, List, Dict, Any, Tuple
from decimal import Decimal


def generate_referral_code(length: int = 7) -> str:
    """
    Generate a random alphanumeric referral code.

    Args:
        length: Length of the code (default: 7)

    Returns:
        Random alphanumeric code (uppercase letters and numbers)

    Example:
        >>> code = generate_referral_code()
        >>> len(code)
        7
        >>> code.isalnum()
        True
    """
    # Use uppercase letters and digits for readability (no O/0 confusion with proper font)
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


def is_valid_referral_code(code: str) -> bool:
    """
    Validate referral code format.

    Args:
        code: Referral code to validate

    Returns:
        True if code is valid format

    Rules:
        - 3-7 characters
        - Alphanumeric only (letters and numbers)
        - Case insensitive
    """
    if not code:
        return False

    # Remove whitespace
    code = code.strip()

    # Check length
    if len(code) < 3 or len(code) > 7:
        return False

    # Check alphanumeric
    if not code.isalnum():
        return False

    return True


def calculate_trade_points(volume_usdt: float) -> Decimal:
    """
    Calculate points earned from a trade.

    Args:
        volume_usdt: Trade volume in USDT

    Returns:
        Points earned (1 point per $1)
    """
    return Decimal(str(volume_usdt))


def calculate_referral_trade_points(volume_usdt: float) -> Decimal:
    """
    Calculate points earned from a referred user's trade.

    Args:
        volume_usdt: Referred user's trade volume in USDT

    Returns:
        Points earned (10% = 0.1 point per $1)
    """
    return Decimal(str(volume_usdt)) * Decimal('0.1')


def get_referral_signup_bonus() -> Decimal:
    """
    Get signup bonus points for referring a new user.

    Returns:
        Signup bonus points (100 points)
    """
    return Decimal('100')


class ReferralManager:
    """
    Manage referrals and points in the database.

    Uses the UserStorage connection for database operations.
    """

    def __init__(self, storage):
        """
        Initialize referral manager.

        Args:
            storage: UserStorage instance
        """
        self.storage = storage

    def generate_unique_code(self, max_attempts: int = 10) -> Optional[str]:
        """
        Generate a unique referral code that doesn't exist in the database.

        Args:
            max_attempts: Maximum attempts to generate unique code

        Returns:
            Unique referral code or None if failed
        """
        for _ in range(max_attempts):
            code = generate_referral_code()

            # Check if code already exists
            if not self.get_user_by_referral_code(code):
                return code

        return None

    def get_user_by_referral_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Get user by their referral code.

        Args:
            code: Referral code (case insensitive)

        Returns:
            User data dict or None if not found
        """
        self.storage._ensure_connection()

        try:
            with self.storage.conn.cursor() as cur:
                cur.execute(
                    "SELECT telegram_id, telegram_username, referral_code, total_points, total_volume "
                    "FROM wallets WHERE UPPER(referral_code) = UPPER(%s)",
                    (code,)
                )
                result = cur.fetchone()

                if result:
                    return {
                        'telegram_id': result[0],
                        'telegram_username': result[1],
                        'referral_code': result[2],
                        'total_points': float(result[3] or 0),
                        'total_volume': float(result[4] or 0),
                    }
                return None
        except Exception as e:
            print(f"Error getting user by referral code: {e}")
            return None

    def set_referral_code(self, telegram_id: int, code: str) -> Tuple[bool, str]:
        """
        Set or update user's referral code.

        Args:
            telegram_id: Telegram user ID
            code: New referral code

        Returns:
            Tuple of (success, message)
        """
        # Validate code format
        if not is_valid_referral_code(code):
            return False, "Invalid code format. Use 3-7 alphanumeric characters."

        code = code.upper().strip()

        # Check if code is already taken
        existing = self.get_user_by_referral_code(code)
        if existing and existing['telegram_id'] != str(telegram_id):
            return False, "This code is already taken. Please choose another."

        self.storage._ensure_connection()

        try:
            with self.storage.conn.cursor() as cur:
                cur.execute(
                    "UPDATE wallets SET referral_code = %s WHERE telegram_id = %s",
                    (code, str(telegram_id))
                )
                self.storage.conn.commit()
                return True, f"Referral code updated to: {code}"
        except Exception as e:
            self.storage.conn.rollback()
            print(f"Error setting referral code: {e}")
            return False, "Failed to update referral code."

    def get_or_create_referral_code(self, telegram_id: int) -> Optional[str]:
        """
        Get user's referral code or create one if they don't have one.

        Args:
            telegram_id: Telegram user ID

        Returns:
            Referral code or None if failed
        """
        self.storage._ensure_connection()

        try:
            # Check if user already has a code
            with self.storage.conn.cursor() as cur:
                cur.execute(
                    "SELECT referral_code FROM wallets WHERE telegram_id = %s",
                    (str(telegram_id),)
                )
                result = cur.fetchone()

                if result and result[0]:
                    return result[0]

            # Generate new unique code
            code = self.generate_unique_code()
            if not code:
                return None

            # Save to database
            with self.storage.conn.cursor() as cur:
                cur.execute(
                    "UPDATE wallets SET referral_code = %s WHERE telegram_id = %s",
                    (code, str(telegram_id))
                )
                self.storage.conn.commit()

            return code
        except Exception as e:
            self.storage.conn.rollback()
            print(f"Error getting/creating referral code: {e}")
            return None

    def set_referred_by(self, telegram_id: int, referral_code: str) -> Tuple[bool, str]:
        """
        Set who referred this user (can only be set once).

        Args:
            telegram_id: Telegram user ID of the new user
            referral_code: Referral code of the referring user

        Returns:
            Tuple of (success, message)
        """
        # Check if user already has a referrer
        self.storage._ensure_connection()

        try:
            with self.storage.conn.cursor() as cur:
                cur.execute(
                    "SELECT referred_by FROM wallets WHERE telegram_id = %s",
                    (str(telegram_id),)
                )
                result = cur.fetchone()

                if result and result[0]:
                    return False, "You were already referred by someone."

            # Validate referral code exists
            referrer = self.get_user_by_referral_code(referral_code)
            if not referrer:
                return False, "Invalid referral code."

            # Can't refer yourself
            if referrer['telegram_id'] == str(telegram_id):
                return False, "You can't refer yourself."

            # Set referrer
            with self.storage.conn.cursor() as cur:
                cur.execute(
                    "UPDATE wallets SET referred_by = UPPER(%s) WHERE telegram_id = %s",
                    (referral_code, str(telegram_id))
                )
                self.storage.conn.commit()

            # Award signup bonus to referrer
            self.add_points(
                telegram_id=int(referrer['telegram_id']),
                points=get_referral_signup_bonus(),
                points_type='referral_signup',
                description=f"Referred new user",
                referred_user_id=str(telegram_id)
            )

            return True, f"Successfully registered with referral code: {referral_code}"
        except Exception as e:
            self.storage.conn.rollback()
            print(f"Error setting referred_by: {e}")
            return False, "Failed to register referral."

    def add_points(
        self,
        telegram_id: int,
        points: Decimal,
        points_type: str,
        volume: Optional[float] = None,
        market_id: Optional[int] = None,
        market_title: Optional[str] = None,
        referred_user_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> bool:
        """
        Add points to a user and record in history.

        Args:
            telegram_id: Telegram user ID
            points: Points to add
            points_type: Type of points ('trade', 'referral_trade', 'referral_signup')
            volume: Trade volume (for trade types)
            market_id: Market ID (for trades)
            market_title: Market title (for trades)
            referred_user_id: Referred user's telegram_id (for referral types)
            description: Additional description

        Returns:
            True if successful
        """
        self.storage._ensure_connection()

        try:
            with self.storage.conn.cursor() as cur:
                # Update total points and volume
                if volume:
                    cur.execute(
                        "UPDATE wallets SET "
                        "total_points = COALESCE(total_points, 0) + %s, "
                        "total_volume = COALESCE(total_volume, 0) + %s "
                        "WHERE telegram_id = %s",
                        (points, volume, str(telegram_id))
                    )
                else:
                    cur.execute(
                        "UPDATE wallets SET total_points = COALESCE(total_points, 0) + %s "
                        "WHERE telegram_id = %s",
                        (points, str(telegram_id))
                    )

                # Record in history
                cur.execute(
                    "INSERT INTO points_history "
                    "(telegram_id, points_earned, points_type, volume, market_id, market_title, "
                    "referred_user_id, description) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (str(telegram_id), points, points_type, volume, market_id, market_title,
                     referred_user_id, description)
                )

                self.storage.conn.commit()
                return True
        except Exception as e:
            self.storage.conn.rollback()
            print(f"Error adding points: {e}")
            return False

    def record_trade_points(
        self,
        telegram_id: int,
        volume_usdt: float,
        market_id: int,
        market_title: str
    ) -> bool:
        """
        Record points for a trade and award referral points if applicable.

        Args:
            telegram_id: User who made the trade
            volume_usdt: Trade volume in USDT
            market_id: Market ID
            market_title: Market title

        Returns:
            True if successful
        """
        # Award points to trader (1 point per $1)
        trade_points = calculate_trade_points(volume_usdt)
        success = self.add_points(
            telegram_id=telegram_id,
            points=trade_points,
            points_type='trade',
            volume=volume_usdt,
            market_id=market_id,
            market_title=market_title,
            description=f"Trade on {market_title[:50]}"
        )

        if not success:
            return False

        # Award referral points to referrer if exists
        self.storage._ensure_connection()

        try:
            with self.storage.conn.cursor() as cur:
                cur.execute(
                    "SELECT referred_by FROM wallets WHERE telegram_id = %s",
                    (str(telegram_id),)
                )
                result = cur.fetchone()

                if result and result[0]:
                    referral_code = result[0]

                    # Get referrer's telegram_id
                    referrer = self.get_user_by_referral_code(referral_code)
                    if referrer:
                        # Award 10% of points to referrer
                        referral_points = calculate_referral_trade_points(volume_usdt)
                        self.add_points(
                            telegram_id=int(referrer['telegram_id']),
                            points=referral_points,
                            points_type='referral_trade',
                            volume=volume_usdt,
                            market_id=market_id,
                            market_title=market_title,
                            referred_user_id=str(telegram_id),
                            description=f"Referral trade on {market_title[:30]}"
                        )
        except Exception as e:
            print(f"Error awarding referral points: {e}")

        return True

    def get_user_points(self, telegram_id: int) -> Dict[str, Any]:
        """
        Get user's points and stats.

        Args:
            telegram_id: Telegram user ID

        Returns:
            Dict with points data
        """
        self.storage._ensure_connection()

        try:
            with self.storage.conn.cursor() as cur:
                cur.execute(
                    "SELECT total_points, total_volume, referral_code, referred_by "
                    "FROM wallets WHERE telegram_id = %s",
                    (str(telegram_id),)
                )
                result = cur.fetchone()

                if not result:
                    return {
                        'total_points': 0,
                        'total_volume': 0,
                        'referral_code': None,
                        'referred_by': None,
                        'referrals_count': 0,
                        'referrals_points': 0,
                    }

                total_points, total_volume, referral_code, referred_by = result

                # Get referrals count
                cur.execute(
                    "SELECT COUNT(*) FROM wallets WHERE UPPER(referred_by) = UPPER(%s)",
                    (referral_code or '',)
                )
                referrals_count = cur.fetchone()[0]

                # Get points from referrals
                cur.execute(
                    "SELECT COALESCE(SUM(points_earned), 0) FROM points_history "
                    "WHERE telegram_id = %s AND points_type IN ('referral_trade', 'referral_signup')",
                    (str(telegram_id),)
                )
                referrals_points = cur.fetchone()[0]

                return {
                    'total_points': float(total_points or 0),
                    'total_volume': float(total_volume or 0),
                    'referral_code': referral_code,
                    'referred_by': referred_by,
                    'referrals_count': referrals_count,
                    'referrals_points': float(referrals_points or 0),
                }
        except Exception as e:
            print(f"Error getting user points: {e}")
            return {
                'total_points': 0,
                'total_volume': 0,
                'referral_code': None,
                'referred_by': None,
                'referrals_count': 0,
                'referrals_points': 0,
            }

    def get_referrals_list(self, telegram_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get list of users referred by this user.

        Args:
            telegram_id: Telegram user ID
            limit: Maximum number of referrals to return

        Returns:
            List of referral data dicts
        """
        self.storage._ensure_connection()

        try:
            # Get user's referral code
            with self.storage.conn.cursor() as cur:
                cur.execute(
                    "SELECT referral_code FROM wallets WHERE telegram_id = %s",
                    (str(telegram_id),)
                )
                result = cur.fetchone()

                if not result or not result[0]:
                    return []

                referral_code = result[0]

                # Get referred users
                cur.execute(
                    "SELECT telegram_username, total_points, total_volume, created_at "
                    "FROM wallets "
                    "WHERE UPPER(referred_by) = UPPER(%s) "
                    "ORDER BY created_at DESC "
                    "LIMIT %s",
                    (referral_code, limit)
                )
                results = cur.fetchall()

                return [
                    {
                        'username': row[0] or 'Anonymous',
                        'total_points': float(row[1] or 0),
                        'total_volume': float(row[2] or 0),
                        'joined_at': row[3],
                    }
                    for row in results
                ]
        except Exception as e:
            print(f"Error getting referrals list: {e}")
            return []
