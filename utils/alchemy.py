"""
Alchemy API Integration for Webhook Management

This module provides functions to programmatically register and manage
Alchemy webhooks for monitoring user wallet activity.
"""

import os
import logging
import requests
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Alchemy API endpoints
ALCHEMY_API_BASE = "https://dashboard.alchemy.com/api"
ALCHEMY_WEBHOOK_ENDPOINT = f"{ALCHEMY_API_BASE}/create-webhook"
ALCHEMY_UPDATE_WEBHOOK_ENDPOINT = f"{ALCHEMY_API_BASE}/update-webhook-addresses"
ALCHEMY_LIST_WEBHOOKS_ENDPOINT = f"{ALCHEMY_API_BASE}/team-webhooks"


def get_alchemy_headers() -> Dict[str, str]:
    """Get headers for Alchemy API requests."""
    api_key = os.getenv("ALCHEMY_API_KEY")
    if not api_key:
        raise ValueError("ALCHEMY_API_KEY environment variable not set")

    return {
        "Content-Type": "application/json",
        "X-Alchemy-Token": api_key
    }


def register_webhook_for_address(address: str) -> Optional[Dict[str, Any]]:
    """
    Register an Alchemy webhook for a new user address.

    Args:
        address: Ethereum/BNB Chain address to monitor

    Returns:
        Webhook data if successful, None otherwise
    """
    try:
        webhook_url = os.getenv("ALCHEMY_WEBHOOK_URL")
        if not webhook_url:
            logger.warning("ALCHEMY_WEBHOOK_URL not set - skipping webhook registration")
            return None

        headers = get_alchemy_headers()

        payload = {
            "network": "BNB_MAINNET",
            "webhook_type": "ADDRESS_ACTIVITY",
            "webhook_url": webhook_url,
            "addresses": [address.lower()]
        }

        response = requests.post(
            ALCHEMY_WEBHOOK_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            logger.info(f"Registered Alchemy webhook for address: {address}")
            return data
        else:
            logger.error(f"Failed to register webhook: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error registering Alchemy webhook: {e}")
        return None


def add_addresses_to_webhook(webhook_id: str, addresses: List[str]) -> bool:
    """
    Add addresses to an existing webhook.

    Args:
        webhook_id: Webhook ID to update
        addresses: List of addresses to add

    Returns:
        True if successful, False otherwise
    """
    try:
        headers = get_alchemy_headers()

        payload = {
            "webhook_id": webhook_id,
            "addresses_to_add": [addr.lower() for addr in addresses],
            "addresses_to_remove": []
        }

        response = requests.patch(
            ALCHEMY_UPDATE_WEBHOOK_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            logger.info(f"Added {len(addresses)} addresses to webhook {webhook_id}")
            return True
        else:
            logger.error(f"Failed to update webhook: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Error updating Alchemy webhook: {e}")
        return False


def remove_addresses_from_webhook(webhook_id: str, addresses: List[str]) -> bool:
    """
    Remove addresses from an existing webhook.

    Args:
        webhook_id: Webhook ID to update
        addresses: List of addresses to remove

    Returns:
        True if successful, False otherwise
    """
    try:
        headers = get_alchemy_headers()

        payload = {
            "webhook_id": webhook_id,
            "addresses_to_add": [],
            "addresses_to_remove": [addr.lower() for addr in addresses]
        }

        response = requests.patch(
            ALCHEMY_UPDATE_WEBHOOK_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            logger.info(f"Removed {len(addresses)} addresses from webhook {webhook_id}")
            return True
        else:
            logger.error(f"Failed to update webhook: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Error updating Alchemy webhook: {e}")
        return False


def list_webhooks() -> List[Dict[str, Any]]:
    """
    List all webhooks for the Alchemy account.

    Returns:
        List of webhook data
    """
    try:
        headers = get_alchemy_headers()

        response = requests.get(
            ALCHEMY_LIST_WEBHOOKS_ENDPOINT,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            webhooks = data.get("data", [])
            logger.info(f"Retrieved {len(webhooks)} webhooks")
            return webhooks
        else:
            logger.error(f"Failed to list webhooks: {response.status_code} - {response.text}")
            return []

    except Exception as e:
        logger.error(f"Error listing Alchemy webhooks: {e}")
        return []


def get_or_create_address_webhook(address: str) -> Optional[str]:
    """
    Get existing webhook ID or create a new one for the address.

    This function checks if there's an existing ADDRESS_ACTIVITY webhook
    for BNB_MAINNET and adds the address to it, or creates a new webhook
    if none exists.

    Args:
        address: Address to monitor

    Returns:
        Webhook ID if successful, None otherwise
    """
    try:
        webhook_url = os.getenv("ALCHEMY_WEBHOOK_URL")
        if not webhook_url:
            logger.warning("ALCHEMY_WEBHOOK_URL not set - skipping webhook setup")
            return None

        # List existing webhooks
        webhooks = list_webhooks()

        # Find existing ADDRESS_ACTIVITY webhook for BNB_MAINNET
        for webhook in webhooks:
            if (webhook.get("type") == "ADDRESS_ACTIVITY" and
                webhook.get("network") == "BNB_MAINNET" and
                webhook.get("webhook_url") == webhook_url):

                webhook_id = webhook.get("id")
                logger.info(f"Found existing webhook: {webhook_id}")

                # Add address to existing webhook
                if add_addresses_to_webhook(webhook_id, [address]):
                    return webhook_id
                else:
                    logger.error("Failed to add address to existing webhook")
                    return None

        # No existing webhook found - create new one
        logger.info("No existing webhook found - creating new one")
        result = register_webhook_for_address(address)

        if result:
            return result.get("id")
        else:
            return None

    except Exception as e:
        logger.error(f"Error in get_or_create_address_webhook: {e}")
        return None


def sync_all_user_addresses():
    """
    Sync all user addresses from database to Alchemy webhook.

    This function should be called during bot startup to ensure all
    existing user addresses are being monitored.
    """
    try:
        from utils.storage import get_storage

        storage = get_storage()

        # Get all wallet addresses
        result = storage.execute_query("SELECT address FROM wallets")

        if not result:
            logger.info("No wallet addresses found in database")
            return

        addresses = [row[0] for row in result]
        logger.info(f"Syncing {len(addresses)} addresses to Alchemy webhook")

        # Get or create webhook and add all addresses
        webhook_url = os.getenv("ALCHEMY_WEBHOOK_URL")
        if not webhook_url:
            logger.warning("ALCHEMY_WEBHOOK_URL not set - skipping sync")
            return

        # Find existing webhook
        webhooks = list_webhooks()
        webhook_id = None

        for webhook in webhooks:
            if (webhook.get("type") == "ADDRESS_ACTIVITY" and
                webhook.get("network") == "BNB_MAINNET" and
                webhook.get("webhook_url") == webhook_url):
                webhook_id = webhook.get("id")
                break

        if webhook_id:
            # Add all addresses to existing webhook
            add_addresses_to_webhook(webhook_id, addresses)
        else:
            # Create new webhook with first address
            if addresses:
                result = register_webhook_for_address(addresses[0])
                if result:
                    webhook_id = result.get("id")
                    # Add remaining addresses
                    if len(addresses) > 1:
                        add_addresses_to_webhook(webhook_id, addresses[1:])

        logger.info("Address sync completed")

    except Exception as e:
        logger.error(f"Error syncing addresses to Alchemy: {e}")
