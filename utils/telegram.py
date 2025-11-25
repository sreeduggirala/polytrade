"""
Telegram Integration for Polymarket Trading Cards

Python conversion of telegram.rs, adapted for Polymarket.
Handles downloading user profile pictures and generating trading cards.
"""

import asyncio
from pathlib import Path
from typing import Optional
from telegram import Bot, User

# Import the card generator from utils
from utils.card import TradingCard


async def download_user_profile_pic(bot: Bot, user_id: int) -> Optional[Path]:
    """
    Download a user's profile picture from Telegram.

    Equivalent to Rust's download_user_profile_pic function.

    Args:
        bot: Telegram Bot instance
        user_id: User's Telegram ID

    Returns:
        Path to the downloaded profile picture, or None if not found
    """
    # Create profile_pics directory if it doesn't exist
    profile_dir = Path("profile_pics")
    profile_dir.mkdir(exist_ok=True)

    try:
        # Get user's profile photos
        photos = await bot.get_user_profile_photos(user_id, limit=1)

        if photos.total_count > 0 and len(photos.photos) > 0:
            # Get the largest photo from the first photo set
            photo = photos.photos[0][-1]

            # Download the file
            file = await bot.get_file(photo.file_id)
            file_path = profile_dir / f"{user_id}.jpg"

            await file.download_to_drive(file_path)
            return file_path

        return None

    except Exception as e:
        print(f"Error downloading profile picture: {e}")
        return None


def get_display_name(user: User) -> str:
    """
    Get user's display name with fallback.

    Equivalent to Rust's get_display_name function.

    Args:
        user: Telegram User object

    Returns:
        Username or first name as fallback
    """
    return user.username if user.username else user.first_name


async def generate_card_for_user(
    bot: Bot,
    user: User,
    market: str,
    position_type: str,
    pnl_amount: float,
    avg_price: float,
    current_price: float,
    shares: float,
) -> Path:
    """
    Generate a trading card for a Telegram user with their profile picture.

    Adapted for Polymarket (no leverage, uses shares instead).
    Equivalent to Rust's generate_card_for_user function.

    Args:
        bot: Telegram Bot instance
        user: Telegram User object
        market: Market name/description (e.g., "BTC > $100k by EOY")
        position_type: "YES" or "NO"
        pnl_amount: Profit/Loss amount in dollars
        avg_price: Average entry price (0.0-1.0)
        current_price: Current market price (0.0-1.0)
        shares: Number of outcome token shares held

    Returns:
        Path to the generated card image

    Raises:
        Exception: If card generation fails
    """
    # Download user's profile picture
    profile_pic_path = await download_user_profile_pic(bot, user.id)

    # Get username or fallback to first name
    username = get_display_name(user)

    # Create trading card with Opinion prediction market data
    card = TradingCard(
        username=username,
        market=market,  # Full market name
        position_type=position_type,  # "YES" or "NO"
        pnl_amount=pnl_amount,
        avg_price=avg_price,  # Average entry price (0.0-1.0)
        current_price=current_price,  # Current market price (0.0-1.0)
        shares=shares,  # Number of shares held
        user_icon_path=str(profile_pic_path) if profile_pic_path else None,
    )

    # Generate and save card
    output_dir = Path("cards")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{user.id}.png"

    card.save(str(output_path))
    return output_path


async def generate_card_for_position(
    bot: Bot,
    user: User,
    position,  # polymarket.Position object
) -> Path:
    """
    Generate a trading card from an Polymarket Position object.

    Convenience wrapper around generate_card_for_user that extracts
    data from an Polymarket Position object.

    Args:
        bot: Telegram Bot instance
        user: Telegram User object
        position: polymarket.Position object with market data

    Returns:
        Path to the generated card image
    """
    return await generate_card_for_user(
        bot=bot,
        user=user,
        market=position.marketTitle,
        position_type=position.tokenName,  # "YES" or "NO"
        pnl_amount=position.unrealizedPnl + position.realizedPnl,
        avg_price=position.avgPrice,
        current_price=position.currentPrice,
        shares=position.shares,
    )


async def main():
    """Example usage."""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    # Initialize bot
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Please set TELEGRAM_BOT_TOKEN environment variable")
        return

    bot = Bot(token=token)

    print("Telegram integration module loaded successfully")
    print("\nAvailable functions:")
    print("  - download_user_profile_pic(bot, user_id)")
    print("  - get_display_name(user)")
    print("  - generate_card_for_user(bot, user, ...)")
    print("  - generate_card_for_position(bot, user, position)")


if __name__ == "__main__":
    asyncio.run(main())
