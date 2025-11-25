"""
User management utilities for multi-user Polymarket bot operations.

This module provides helper functions to get user-specific clients and account managers.
"""

import os
from typing import Optional, Dict, Any
from telegram.ext import ContextTypes

from utils.storage import get_storage
from utils.account import AccountManager, create_new_account
from utils.polymarket_client import PolymarketClient

# Signature type for Polymarket (1 = proxy wallet)
SIGNATURE_TYPE = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "1"))


# Default settings for new users
DEFAULT_USER_SETTINGS = {
    "confirm_trades": True,
    "show_pnl": True,
    "show_charts": True,
    "language": "en",
    "default_bet": 25,  # Default bet amount in USDC
    # Copytrading settings
    "copytrading_enabled": True,
    "copytrading_notifications": True,
    "default_scale_factor": 0.25,
}


def get_user_private_key(telegram_id: int) -> Optional[str]:
    """
    Get private key for a user.

    Falls back to PRIVATE_KEY environment variable for backwards compatibility
    with single-user mode.

    Args:
        telegram_id: Telegram user ID

    Returns:
        Private key or None if not found
    """
    storage = get_storage()

    # Try to get from database first
    private_key = storage.get_private_key(telegram_id)

    # Fallback to environment variable (single-user mode)
    if not private_key:
        private_key = os.getenv("PRIVATE_KEY")

    return private_key


def get_user_wallet_address(telegram_id: int) -> Optional[str]:
    """
    Get wallet address for a user.

    Falls back to POLYMARKET_PROXY_ADDRESS for single-user mode.
    """
    storage = get_storage()
    address = storage.get_wallet_address(telegram_id)

    if not address:
        address = os.getenv("POLYMARKET_PROXY_ADDRESS")

    return address


def get_user_account_manager(telegram_id: int, testnet: bool = False) -> Optional[AccountManager]:
    """
    Get AccountManager instance for a user (for on-chain operations).

    Args:
        telegram_id: Telegram user ID
        testnet: Whether to use testnet

    Returns:
        AccountManager instance or None if user has no wallet
    """
    private_key = get_user_private_key(telegram_id)
    if not private_key:
        return None

    return AccountManager(private_key=private_key, testnet=testnet)


def get_user_polymarket_client(telegram_id: int) -> Optional[PolymarketClient]:
    """
    Get PolymarketClient instance for a user.

    Args:
        telegram_id: Telegram user ID

    Returns:
        PolymarketClient instance or None if user has no wallet
    """
    private_key = get_user_private_key(telegram_id)
    if not private_key:
        return None

    funder_address = get_user_wallet_address(telegram_id)
    if not funder_address:
        funder_address = private_key  # Use derived address

    return PolymarketClient(
        private_key=private_key,
        funder_address=funder_address,
        signature_type=SIGNATURE_TYPE,
    )


# Backwards compatibility alias
get_user_polymarket_client = get_user_polymarket_client


def create_user_wallet(telegram_id: int, telegram_username: Optional[str] = None, testnet: bool = False) -> Dict[str, str]:
    """
    Create a new wallet for a user and store it.

    Args:
        telegram_id: Telegram user ID
        telegram_username: Telegram username (optional)
        testnet: Whether to create testnet wallet

    Returns:
        Dictionary with 'address' and 'private_key'
    """
    storage = get_storage()

    # Create new account
    account_mgr, account_info = create_new_account(testnet=testnet)

    # Store in database
    storage.save_wallet(
        telegram_id=telegram_id,
        wallet_address=account_info['address'],
        private_key=account_info['private_key'],
        telegram_username=telegram_username
    )

    # Initialize default settings
    storage.save_settings(telegram_id, DEFAULT_USER_SETTINGS.copy())

    # Register Alchemy webhook for deposit/withdrawal notifications
    try:
        from utils.alchemy import get_or_create_address_webhook
        get_or_create_address_webhook(account_info['address'])
    except Exception as e:
        # Don't fail wallet creation if webhook registration fails
        import logging
        logging.getLogger(__name__).warning(f"Failed to register Alchemy webhook: {e}")

    return account_info


def import_user_wallet(telegram_id: int, private_key: str, telegram_username: Optional[str] = None, testnet: bool = False) -> Dict[str, str]:
    """
    Import an existing wallet for a user.

    Args:
        telegram_id: Telegram user ID
        private_key: Private key to import
        testnet: Whether wallet is for testnet

    Returns:
        Dictionary with 'address' and 'private_key'

    Raises:
        ValueError: If private key is invalid
    """
    storage = get_storage()

    # Validate by creating AccountManager
    try:
        account_mgr = AccountManager(private_key=private_key, testnet=testnet)
        wallet_address = account_mgr.get_address()
    except Exception as e:
        raise ValueError(f"Invalid private key: {e}")

    # Store in database
    storage.save_wallet(
        telegram_id=telegram_id,
        wallet_address=wallet_address,
        private_key=private_key,
        telegram_username=telegram_username
    )

    # Initialize default settings if user doesn't have them
    if not storage.get_settings(telegram_id):
        storage.save_settings(telegram_id, DEFAULT_USER_SETTINGS.copy())

    # Register Alchemy webhook for deposit/withdrawal notifications
    try:
        from utils.alchemy import get_or_create_address_webhook
        get_or_create_address_webhook(wallet_address)
    except Exception as e:
        # Don't fail wallet import if webhook registration fails
        import logging
        logging.getLogger(__name__).warning(f"Failed to register Alchemy webhook: {e}")

    return {
        'address': wallet_address,
        'private_key': private_key
    }


def delete_user_wallet(telegram_id: int) -> bool:
    """
    Delete a user's wallet.

    Args:
        telegram_id: Telegram user ID

    Returns:
        True if successful
    """
    storage = get_storage()
    return storage.delete_wallet(telegram_id)


def get_user_settings(telegram_id: int) -> Dict[str, Any]:
    """
    Get user settings, creating defaults if none exist.

    Args:
        telegram_id: Telegram user ID

    Returns:
        Settings dictionary
    """
    storage = get_storage()
    settings = storage.get_settings(telegram_id)

    if not settings:
        settings = DEFAULT_USER_SETTINGS.copy()
        storage.save_settings(telegram_id, settings)

    return settings


def update_user_settings(telegram_id: int, settings: Dict[str, Any]) -> bool:
    """
    Update user settings.

    Args:
        telegram_id: Telegram user ID
        settings: Settings dictionary

    Returns:
        True if successful
    """
    storage = get_storage()
    return storage.save_settings(telegram_id, settings)


def has_user_wallet(telegram_id: int) -> bool:
    """
    Check if user has a wallet.

    Falls back to checking PRIVATE_KEY for backwards compatibility.

    Args:
        telegram_id: Telegram user ID

    Returns:
        True if user has wallet
    """
    storage = get_storage()

    # Check database first
    if storage.has_wallet(telegram_id):
        return True

    # Fallback to environment variable (single-user mode)
    return os.getenv("PRIVATE_KEY") is not None


def get_telegram_user_id(context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Extract Telegram user ID from context.

    Args:
        context: Telegram context

    Returns:
        User ID
    """
    return context._user_id
