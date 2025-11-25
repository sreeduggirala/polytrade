"""
Polymarket Trading Bot - Telegram Interface

A trading bot for prediction markets on Polymarket (Polygon).
Features inline keyboards, real-time position tracking, shareable trading cards,
and automated copytrading.
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

from dotenv import load_dotenv

# Load environment variables BEFORE importing our utilities
# This ensures .env vars are available when modules initialize
# Use override=True to ensure .env values take precedence over shell env vars
load_dotenv(override=True)

# Import our utilities - using Polymarket client (Polymarket interface)
from utils.polymarket_client import (
    PolymarketClient as PolymarketClient,  # Alias for compatibility
    Market,
    Position,
    OrderSide,
    OrderType,
    PlaceOrderDataInput,
    TopicStatusFilter,
    TopicType,
)
from utils.account import AccountManager
from utils.card import TradingCard, PositionsCard, PnLHistoryCard
from utils.telegram import generate_card_for_position

# Copytrading support
from utils.copytrading import (
    init_copytrading_manager,
    get_copytrading_manager,
    CopySubscription,
    MirrorResult,
)

# Multi-user support
from utils.user_manager import (
    get_user_polymarket_client,  # Now returns PolymarketClient
    get_user_polymarket_client,
    get_user_account_manager,
    create_user_wallet,
    import_user_wallet,
    delete_user_wallet,
    get_user_settings as get_persistent_user_settings,
    update_user_settings as update_persistent_user_settings,
    has_user_wallet,
)
from utils.storage import init_storage, UserStorage

# Initialize storage for multi-user support
init_storage()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
(
    AWAITING_BET_AMOUNT,
    AWAITING_MARKET_SEARCH,
    AWAITING_LIMIT_PRICE,
    AWAITING_WALLET_IMPORT,
    AWAITING_WITHDRAWAL_ADDRESS,
    AWAITING_WITHDRAWAL_AMOUNT,
    # Copytrading states
    AWAITING_COPY_WALLET,
    AWAITING_COPY_NAME,
    AWAITING_COPY_SCALE,
) = range(9)

# User data keys
USER_DATA_MARKET = "current_market"
USER_DATA_SIDE = "current_side"
USER_DATA_WALLET = "wallet_address"
USER_DATA_SETTINGS = "settings"
USER_DATA_COPY_WALLET = "copy_wallet"
USER_DATA_COPY_NAME = "copy_name"


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def get_user_settings(context: ContextTypes.DEFAULT_TYPE) -> Dict[str, Any]:
    """Get or initialize user settings from persistent storage."""
    telegram_id = context._user_id
    return get_persistent_user_settings(telegram_id)


def format_price(price: float) -> str:
    """Format price with $ and 3 decimals."""
    return f"${price:.3f}"


def format_pnl(pnl: float) -> str:
    """Format PnL with color indicator."""
    if pnl >= 0:
        return f"+${pnl:.2f}"
    else:
        return f"-${abs(pnl):.2f}"


def get_pnl_emoji(pnl: float) -> str:
    """Get emoji based on PnL."""
    if pnl > 0:
        return "📈"
    elif pnl < 0:
        return "📉"
    return "➖"


def get_position_emoji(token_name: str, index: int = 0) -> str:
    """
    Get emoji for a position based on token name.

    Args:
        token_name: The token name (YES, NO, or custom option name)
        index: Index for categorical markets (used if not YES/NO)

    Returns:
        Appropriate emoji for the position
    """
    # Binary market tokens
    if token_name == "YES":
        return "✅"
    elif token_name == "NO":
        return "❌"
    # Categorical market tokens - use color emojis
    else:
        emojis = ["🔵", "🟢", "🟡", "🟠", "🔴", "🟣", "🟤", "⚪"]
        return emojis[index % len(emojis)]


# ============================================================================
# MAIN MENU
# ============================================================================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command - show main menu."""
    user = update.effective_user

    # Welcome message
    welcome_text = (
        f"🎯 Welcome to Polymarket Bot, {user.first_name}!\n\n"
        f"Trade prediction markets on Polygon with ease.\n"
        f"Your shareable trading cards are just a tap away.\n\n"
        f"Select an option below to get started:"
    )

    keyboard = get_main_menu_keyboard()

    if update.message:
        await update.message.reply_text(
            welcome_text, reply_markup=keyboard, parse_mode=ParseMode.HTML
        )
    else:
        await update.callback_query.message.edit_text(
            welcome_text, reply_markup=keyboard, parse_mode=ParseMode.HTML
        )


async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Debug command - show database connection and wallet status."""
    telegram_id = update.effective_user.id

    try:
        from utils.storage import get_storage
        import os

        storage = get_storage()

        # Get DATABASE_URL (masked for security)
        db_url = os.getenv("DATABASE_URL", "Not set")
        if db_url and db_url != "Not set":
            # Mask password in connection string
            import re
            db_url_masked = re.sub(r'://([^:]+):([^@]+)@', r'://\1:****@', db_url)
        else:
            db_url_masked = "Not set"

        # Check if wallet exists in database
        has_wallet = storage.has_wallet(telegram_id)
        wallet_address = storage.get_wallet_address(telegram_id) if has_wallet else "None"

        # Try to get all users in database
        try:
            all_users = storage.get_all_active_users()
            user_count = len(all_users)
            user_in_db = telegram_id in all_users
        except Exception as e:
            user_count = f"Error: {e}"
            user_in_db = False

        text = f"🔧 <b>Debug Info</b>\n\n"
        text += f"<b>Your Telegram ID:</b> <code>{telegram_id}</code>\n\n"
        text += f"<b>Database Connection:</b>\n<code>{db_url_masked}</code>\n\n"
        text += f"<b>Wallet in DB:</b> {'✅ Yes' if has_wallet else '❌ No'}\n"
        text += f"<b>Wallet Address:</b> <code>{wallet_address}</code>\n\n"
        text += f"<b>Total Users in DB:</b> {user_count}\n"
        text += f"<b>You in user list:</b> {'✅ Yes' if user_in_db else '❌ No'}\n\n"
        text += f"<i>If wallet shows 'No' but you created one, check DATABASE_URL in Railway matches your Supabase connection string.</i>"

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Debug command error: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Debug error:\n\n<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Get main menu inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("💼 Positions", callback_data="positions"),
            InlineKeyboardButton("🔍 Search", callback_data="search_markets"),
        ],
        [
            InlineKeyboardButton("📋 Copytrading", callback_data="copytrading"),
            InlineKeyboardButton("💰 Wallet", callback_data="wallet"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
            InlineKeyboardButton("❓ Help", callback_data="help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# ============================================================================
# MARKETS BROWSER
# ============================================================================


def deduplicate_markets_by_title(markets: List[Any]) -> List[Any]:
    """
    Deduplicate markets by title, keeping only one per unique title.

    For categorical markets, Polymarket returns each outcome as a separate market.
    This keeps the first market for each unique title.
    """
    seen = {}
    unique = []

    for market in markets:
        title = market.marketTitle
        if title not in seen:
            seen[title] = True
            unique.append(market)

    return unique


async def show_markets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show list of active markets (both BINARY and CATEGORICAL)."""
    query = update.callback_query

    # Initialize Polymarket client
    try:
        client = PolymarketClient()

        # Fetch both BINARY and CATEGORICAL markets
        binary_markets = client.get_markets(
            topic_type=TopicType.BINARY,
            status=TopicStatusFilter.ACTIVATED,
            limit=10
        )
        categorical_markets = client.get_markets(
            topic_type=TopicType.CATEGORICAL,
            status=TopicStatusFilter.ACTIVATED,
            limit=10
        )

        # Combine both types
        markets = (binary_markets or []) + (categorical_markets or [])

        logger.info(
            f"Fetched {len(markets) if markets else 0} markets from Polymarket API "
            f"({len(binary_markets or [])} BINARY, {len(categorical_markets or [])} CATEGORICAL)"
        )
        if markets:
            logger.info(f"Sample markets: {[m.marketTitle for m in markets[:3]]}")

        if not markets:
            await query.message.edit_text(
                "📊 No active markets found.\n\n"
                "Try again later or check your connection.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Back", callback_data="start")]]
                ),
            )
            return

        text = "📊 <b>Active Markets</b>\n\n"
        text += "Select a market to view details and place bets:\n\n"

        keyboard = []
        market_count = 0
        for market in markets:
            # Skip concluded/resolving markets (only show CREATED=1 or ACTIVATED=2)
            if market.status >= 3:  # RESOLVING=3 or RESOLVED=4
                logger.info(
                    f"Filtered out concluded market: {market.marketTitle} (status={market.status})"
                )
                continue

            market_count += 1
            if market_count > 10:
                break

            # Truncate long titles
            title = market.marketTitle
            if len(title) > 40:
                title = title[:37] + "..."

            text += f"{market_count}. {title}\n"
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"{market_count}. {title}",
                        callback_data=f"market_{market.marketId}",
                    )
                ]
            )
            logger.debug(f"Market {market_count}: ID={market.marketId}, Title={market.marketTitle[:50]}")

        logger.info(f"Showing {market_count} active markets")

        keyboard.append(
            [InlineKeyboardButton("« Back", callback_data="start")]
        )

        await query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Error fetching markets: {e}")
        await query.message.edit_text(
            "❌ Error loading markets. Please try again.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Back", callback_data="start")]]
            ),
        )


async def initiate_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Initiate market search - prompt user for keyword."""
    query = update.callback_query

    text = (
        "🔍 <b>Search Markets</b>\n\n"
        "Enter a keyword to search for markets.\n\n"
        "<i>Examples: bitcoin, trump, election, AI, sports</i>\n\n"
        "Type your search term below:"
    )

    keyboard = [[InlineKeyboardButton("« Cancel", callback_data="start")]]

    await query.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )

    return AWAITING_MARKET_SEARCH


async def handle_search_query(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle market search query from user."""
    message = update.message
    keyword = message.text.strip()

    if not keyword:
        await message.reply_text(
            "❌ Please enter a valid search term.\n\n"
            "Try again or use /start to return to main menu."
        )
        return AWAITING_MARKET_SEARCH

    # Show searching message with cache status
    from utils.polymarket_client import _GLOBAL_MARKETS_CACHE, _GLOBAL_MARKETS_CACHE_TIME
    import time

    cache_age = time.time() - _GLOBAL_MARKETS_CACHE_TIME
    is_cached = _GLOBAL_MARKETS_CACHE and cache_age < 300  # 5 minute TTL

    if is_cached:
        search_msg = await message.reply_text(
            f"🔍 Searching for '<b>{keyword}</b>'...", parse_mode=ParseMode.HTML
        )
    else:
        search_msg = await message.reply_text(
            f"🔍 Searching for '<b>{keyword}</b>'...\n\n"
            f"<i>Searching first 100 markets (2-3 seconds)...</i>",
            parse_mode=ParseMode.HTML
        )

    try:
        # Initialize Polymarket client and search first 100 markets (5 pages) for speed
        # This keeps searches under 3 seconds instead of 6+ minutes
        client = PolymarketClient()
        all_results = client.search_markets(keyword, max_results=50, max_pages=5)

        if not all_results:
            await search_msg.edit_text(
                f"🔍 <b>No Results Found</b>\n\n"
                f"No markets found matching '<b>{keyword}</b>'.\n\n"
                f"Try a different search term or browse all markets.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "📊 Browse All Markets", callback_data="markets"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🔍 New Search", callback_data="search_markets"
                            )
                        ],
                        [InlineKeyboardButton("« Back", callback_data="start")],
                    ]
                ),
                parse_mode=ParseMode.HTML,
            )
            return ConversationHandler.END

        # search_markets already filters by status="ACTIVATED" by default
        logger.info(f"Search for '{keyword}' found {len(all_results)} markets before deduplication")

        # Log first few markets for debugging
        for i, m in enumerate(all_results[:5]):
            logger.info(f"  Market {i}: ID={m.marketId}, Title={m.marketTitle[:50]}, Type={m.marketType}, Status={m.status}")

        # Deduplicate by title (categorical markets have multiple outcomes)
        results = deduplicate_markets_by_title(all_results)

        logger.info(f"After deduplication: {len(results)} unique markets")

        # Log deduplicated results
        for i, m in enumerate(results[:5]):
            logger.info(f"  Deduplicated {i}: ID={m.marketId}, Title={m.marketTitle[:50]}, Type={m.marketType}")

        # Display search results
        text = f"🔍 <b>Search Results for '{keyword}'</b>\n\n"
        text += f"Found {len(results)} market(s)"
        if not is_cached:
            text += f" (searched first 100 markets)"
        text += f":\n\n"

        # Store search results in context for callback lookup
        # (Telegram has 64-byte limit on callback data, so we can't store full titles)
        context.user_data["search_results"] = {i: market.marketTitle for i, market in enumerate(results[:20])}

        keyboard = []
        for i, market in enumerate(results[:20], 1):  # Show top 20
            # Truncate long titles for display
            title = market.marketTitle
            if len(title) > 40:
                title = title[:37] + "..."

            # Use index instead of full title (Telegram callback data limit is 64 bytes)
            callback_data = f"searchres_{i-1}"  # 0-indexed for lookup
            logger.info(f"Creating search result button: {title} | ID: {market.marketId} | Type: {market.marketType}")

            text += f"{i}. {title}\n"
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"{i}. {title}", callback_data=callback_data
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton("🔍 New Search", callback_data="search_markets"),
                InlineKeyboardButton("« Back", callback_data="start"),
            ]
        )

        await search_msg.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error searching markets: {e}")
        await search_msg.edit_text(
            f"❌ <b>Search Error</b>\n\n"
            f"An error occurred while searching for '<b>{keyword}</b>'.\n\n"
            f"Please try again.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔍 Try Again", callback_data="search_markets"
                        )
                    ],
                    [InlineKeyboardButton("« Back", callback_data="start")],
                ]
            ),
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END


async def handle_search_result_click(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle clicking on a search result - re-search by title to get correct market data."""
    query = update.callback_query
    await query.answer()

    # Get the result index from callback data
    result_index = int(query.data.split("_")[1])

    # Get the market title from stored search results
    search_results = context.user_data.get("search_results", {})
    market_title = search_results.get(result_index)

    if not market_title:
        await query.message.edit_text(
            "❌ Search results expired. Please search again.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔍 Search", callback_data="search_markets")]]
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    logger.info(f"Search result clicked: {market_title}")

    try:
        client = PolymarketClient()

        # Re-search by exact title to get fresh, correct data
        all_markets = client.search_markets(market_title, max_results=100, max_pages=10)

        # Filter to exact title matches
        matches = [m for m in all_markets if m.marketTitle == market_title]

        if not matches:
            await query.message.edit_text(
                f"❌ Market not found: {market_title}\n\nIt may have been deleted or is no longer active.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Back to Search", callback_data="search_markets")]]
                ),
                parse_mode=ParseMode.HTML,
            )
            return

        # Check if this is a categorical market (multiple outcomes with same title)
        if len(matches) > 1:
            # Categorical market - show outcomes list
            logger.info(f"Categorical market with {len(matches)} outcomes")

            text = f"📊 <b>{market_title}</b>\n\n"
            text += f"Select an outcome to trade:\n\n"

            keyboard = []
            for i, outcome in enumerate(matches[:20], 1):  # Show up to 20 outcomes
                # Get outcome label from options if available
                outcome_label = f"Outcome {i}"
                if outcome.options and len(outcome.options) > 0:
                    outcome_label = outcome.options[0].get('label', outcome_label)

                text += f"{i}. {outcome_label}\n"
                keyboard.append([
                    InlineKeyboardButton(
                        f"{i}. {outcome_label}",
                        callback_data=f"market_{outcome.marketId}"
                    )
                ])

            keyboard.append([
                InlineKeyboardButton("« Back to Search", callback_data="search_markets")
            ])

            await query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
        else:
            # Binary market - go straight to trading
            market = matches[0]
            logger.info(f"Binary market ID: {market.marketId}")

            # Show the market details directly
            context.user_data["current_market_id"] = market.marketId

            # Call show_market_details directly
            class FakeQuery:
                def __init__(self, market_id, original_query):
                    self.data = f"market_{market_id}"
                    self.message = original_query.message

                async def answer(self):
                    pass

            fake_query = FakeQuery(market.marketId, query)

            class FakeUpdate:
                def __init__(self):
                    self.callback_query = fake_query
                    self.effective_user = update.effective_user

            await show_market_details(FakeUpdate(), context)

    except Exception as e:
        logger.error(f"Error handling search result click: {e}", exc_info=True)
        await query.message.edit_text(
            f"❌ Error loading market.\n\nError: {str(e)[:100]}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Back to Search", callback_data="search_markets")]]
            ),
        )


async def show_categorical_outcomes(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show all outcomes for a categorical market."""
    query = update.callback_query

    # Extract market ID from callback data: catmarket_{marketId}
    market_id = int(query.data.split("_")[1])

    logger.info(f"Showing outcomes for categorical market ID: {market_id}")

    try:
        client = PolymarketClient()

        # Fetch the specific market to get its title
        base_market = client.get_market(market_id)
        if not base_market:
            await query.message.edit_text(
                f"❌ Market not found.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Back", callback_data="search_markets")]]
                ),
                parse_mode=ParseMode.HTML,
            )
            return

        market_title = base_market.marketTitle
        logger.info(f"Market title: {market_title}")

        # Search for all markets with this exact title to get all outcomes
        all_markets = client.search_markets(market_title, max_results=100, max_pages=10)

        # Filter to exact title matches
        outcomes = [m for m in all_markets if m.marketTitle == market_title]

        if not outcomes:
            await query.message.edit_text(
                f"❌ No outcomes found for this market.\n\n{market_title}",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Back", callback_data="search_markets")]]
                ),
                parse_mode=ParseMode.HTML,
            )
            return

        # Display outcomes list
        text = f"📊 <b>{market_title}</b>\n\n"
        text += f"Select an outcome to trade:\n\n"

        keyboard = []
        for i, outcome in enumerate(outcomes[:20], 1):  # Show up to 20 outcomes
            # Get outcome label from options if available
            outcome_label = f"Outcome {i}"
            if outcome.options and len(outcome.options) > 0:
                outcome_label = outcome.options[0].get('label', outcome_label)

            text += f"{i}. {outcome_label}\n"
            keyboard.append([
                InlineKeyboardButton(
                    f"{i}. {outcome_label}",
                    callback_data=f"market_{outcome.marketId}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton("« Back", callback_data="search_markets")
        ])

        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Error showing categorical outcomes: {e}", exc_info=True)
        await query.message.edit_text(
            f"❌ Error loading outcomes.\n\nError: {str(e)[:100]}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Back", callback_data="search_markets")]]
            ),
        )


async def show_market_details(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show detailed market view with buy/sell buttons."""
    query = update.callback_query

    # Extract market ID from callback data
    market_id = int(query.data.split("_")[1])
    logger.info(f"User clicked market button with ID: {market_id}")

    try:
        client = PolymarketClient()
        market = client.get_market(market_id)

        if not market:
            logger.warning(f"Market {market_id} not found in API")
            await query.message.edit_text(
                "❌ Market not found.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Back", callback_data="markets")]]
                ),
            )
            return

        # Log what we actually got back
        logger.info(f"Fetched market {market.marketId}: {market.marketTitle}")

        # Format market header
        text = f"📊 <b>{market.marketTitle}</b>\n\n"
        text += f"💰 <b>Volume:</b> ${market.volume:,.0f}\n"
        text += f"📈 <b>Status:</b> {'🟢 Active' if market.status == 2 else '🔴 Inactive'}\n"
        text += f"📋 <b>Type:</b> {'Binary' if market.marketType == TopicType.BINARY else 'Categorical'}\n\n"

        # Store market in context
        context.user_data[USER_DATA_MARKET] = market_id

        keyboard = []

        # Handle BINARY markets (YES/NO)
        if market.marketType == TopicType.BINARY:
            # Get labels (fallback to YES/NO if not provided)
            yes_label = market.yesLabel or "YES"
            no_label = market.noLabel or "NO"

            # Get token IDs
            yes_token = market.yesTokenId or (market.tokenIds[0] if market.tokenIds else None)
            no_token = market.noTokenId or (market.tokenIds[1] if len(market.tokenIds) > 1 else None)

            # Fetch prices (no hardcoded defaults)
            yes_price = None
            no_price = None

            if yes_token:
                yes_price = client.get_latest_price(yes_token)

            if no_token:
                no_price = client.get_latest_price(no_token)

            # Skip display if we can't fetch prices
            if yes_price is None or no_price is None:
                text += f"<i>⚠️ Unable to fetch current prices</i>\n\n"
                yes_price = yes_price or 0.5
                no_price = no_price or 0.5

            text += f"<b>Current Prices:</b>\n"
            text += f"✅ {yes_label}: {format_price(yes_price)} ({yes_price*100:.1f}%)\n"
            text += f"❌ {no_label}: {format_price(no_price)} ({no_price*100:.1f}%)\n\n"
            text += "Select your position:"

            keyboard = [
                [
                    InlineKeyboardButton(
                        f"✅ Buy {yes_label} @ {format_price(yes_price)}",
                        callback_data=f"buy_0_{market_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        f"❌ Buy {no_label} @ {format_price(no_price)}",
                        callback_data=f"buy_1_{market_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        f"📝 Limit {yes_label}", callback_data=f"limit_0_{market_id}"
                    ),
                    InlineKeyboardButton(
                        f"📝 Limit {no_label}", callback_data=f"limit_1_{market_id}"
                    ),
                ],
            ]

        # Handle CATEGORICAL markets (multiple outcomes)
        # Show list of sub-markets (options) to choose from
        else:
            text += f"<b>Available Options:</b>\n\n"
            text += "Select an option to view its market:\n\n"

            # Build options list from available data
            options = []
            if market.options:
                options = market.options
            elif market.tokenIds:
                # Fallback: create options from tokenIds
                options = [{"tokenId": tid, "label": f"Option {i+1}"} for i, tid in enumerate(market.tokenIds)]

            # Create buttons for each option (sub-market)
            for i, option in enumerate(options):
                label = option.get("label") or option.get("name") or f"Option {i+1}"
                emoji = ["🔵", "🟢", "🟡", "🟠", "🔴", "🟣", "🟤", "⚪"][i % 8]

                text += f"{i+1}. {emoji} {label}\n"

                # Button goes to sub-market view (option trading page)
                keyboard.append([
                    InlineKeyboardButton(
                        f"{i+1}. {emoji} {label}",
                        callback_data=f"option_{market_id}_{i}",
                    )
                ])

        # Add back button
        keyboard.append([InlineKeyboardButton("« Back", callback_data="markets")])

        await query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Error loading market details: {e}")
        await query.message.edit_text(
            "❌ Error loading market. Please try again.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Back", callback_data="markets")]]
            ),
        )


async def show_option_trading(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show trading interface for a specific categorical market option (treated as binary YES/NO)."""
    query = update.callback_query

    # Parse callback data: option_{market_id}_{option_index}
    parts = query.data.split("_")
    market_id = int(parts[1])
    option_index = int(parts[2])

    try:
        client = PolymarketClient()
        market = client.get_market(market_id)

        if not market:
            await query.message.edit_text(
                "❌ Market not found.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Back", callback_data="markets")]]
                ),
            )
            return

        # Get the specific option
        options = market.options if market.options else []
        if not options and market.tokenIds:
            options = [{"tokenId": tid, "label": f"Option {i+1}"} for i, tid in enumerate(market.tokenIds)]

        if option_index >= len(options):
            await query.message.edit_text(
                "❌ Option not found.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Back", callback_data=f"market_{market_id}")]]
                ),
            )
            return

        option = options[option_index]
        option_label = option.get("label") or option.get("name") or f"Option {option_index + 1}"
        token_id = option.get("tokenId") or option.get("token_id")

        # Fetch price for this option
        price = None
        if token_id:
            price = client.get_latest_price(token_id)

        # Format display
        emoji = ["🔵", "🟢", "🟡", "🟠", "🔴", "🟣", "🟤", "⚪"][option_index % 8]
        text = f"📊 <b>{market.marketTitle}</b>\n\n"
        text += f"{emoji} <b>Option: {option_label}</b>\n\n"
        text += f"💰 <b>Volume:</b> ${market.volume:,.0f}\n"
        text += f"📈 <b>Status:</b> {'🟢 Active' if market.status == 2 else '🔴 Inactive'}\n\n"

        # Store market and option in context
        context.user_data[USER_DATA_MARKET] = market_id
        context.user_data["option_index"] = option_index

        keyboard = []

        if price is not None:
            text += f"<b>Current Price:</b>\n"
            text += f"{emoji} {option_label}: {format_price(price)} ({price*100:.1f}%)\n\n"
            text += "Select your position:"

            keyboard = [
                [
                    InlineKeyboardButton(
                        f"✅ Buy {option_label} @ {format_price(price)}",
                        callback_data=f"buy_{option_index}_{market_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        f"📝 Limit Order {option_label}",
                        callback_data=f"limit_{option_index}_{market_id}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🔄 Refresh", callback_data=f"option_{market_id}_{option_index}"
                    ),
                    InlineKeyboardButton(
                        "« Back", callback_data=f"market_{market_id}"
                    ),
                ],
            ]
        else:
            text += f"<i>⚠️ Unable to fetch current price for {option_label}</i>\n\n"
            keyboard = [
                [
                    InlineKeyboardButton(
                        "🔄 Refresh", callback_data=f"option_{market_id}_{option_index}"
                    ),
                    InlineKeyboardButton(
                        "« Back", callback_data=f"market_{market_id}"
                    ),
                ],
            ]

        await query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Error loading option trading: {e}")
        await query.message.edit_text(
            "❌ Error loading option. Please try again.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Back", callback_data="markets")]]
            ),
        )


# ============================================================================
# TRADING FLOW
# ============================================================================


async def initiate_limit_order(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Initiate limit order flow - ask for price."""
    query = update.callback_query

    # Parse callback data: limit_{index}_{market_id}
    parts = query.data.split("_")
    outcome_index = int(parts[1])  # 0, 1, 2, etc.
    market_id = int(parts[2])

    try:
        client = PolymarketClient()
        market = client.get_market(market_id)

        # Determine outcome label
        if market.marketType == TopicType.BINARY:
            if outcome_index == 0:
                outcome_label = market.yesLabel or "YES"
            else:
                outcome_label = market.noLabel or "NO"
        else:  # CATEGORICAL
            if market.options and outcome_index < len(market.options):
                option = market.options[outcome_index]
                outcome_label = option.get("label") or option.get("name") or f"Option {outcome_index + 1}"
            else:
                outcome_label = f"Option {outcome_index + 1}"

        # Store order info
        context.user_data[USER_DATA_MARKET] = market_id
        context.user_data["outcome_index"] = outcome_index
        context.user_data["outcome_label"] = outcome_label
        context.user_data["order_type"] = "limit"

        # Get current price for reference
        if outcome_index < len(market.tokenIds):
            token_id = market.tokenIds[outcome_index]
            current_price = client.get_latest_price(token_id) or 0.50
        else:
            current_price = 0.50

        text = f"📝 <b>Limit Order - {outcome_label}</b>\n\n"
        text += f"<b>Market:</b> {market.marketTitle[:60]}\n"
        text += f"<b>Current Price:</b> {format_price(current_price)} ({current_price*100:.1f}%)\n\n"
        text += f"Enter your limit price (0.01 - 0.99):\n\n"
        text += f"<i>Example: 0.75</i>\n\n"
        text += f"Your order will execute when the market reaches this price."

        keyboard = [
            [InlineKeyboardButton("« Cancel", callback_data=f"market_{market_id}")]
        ]

        await query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )

        return AWAITING_LIMIT_PRICE

    except Exception as e:
        logger.error(f"Error initiating limit order: {e}")
        await query.message.edit_text(
            "❌ Error preparing limit order. Please try again.",
            reply_markup=get_main_menu_keyboard(),
        )
        return ConversationHandler.END


async def handle_limit_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle limit price input."""
    message = update.message

    try:
        # Parse the price
        price = float(message.text.strip())

        # Validate price (0.01 to 0.99)
        if price <= 0 or price >= 1:
            await message.reply_text(
                "❌ Price must be between 0.01 and 0.99.\n\n"
                "Please enter a valid price:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Cancel", callback_data="start")]]
                ),
            )
            return AWAITING_LIMIT_PRICE

        # Store price
        context.user_data["limit_price"] = price

        # Now ask for amount
        market_id = context.user_data.get(USER_DATA_MARKET)
        side = context.user_data.get(USER_DATA_SIDE)

        text = f"📝 <b>Limit Order - {side} @ {format_price(price)}</b>\n\n"
        text += f"Select bet amount:"

        settings = get_user_settings(context)
        default_bet = settings["default_bet"]

        keyboard = [
            [
                InlineKeyboardButton("$10", callback_data="limit_bet_10"),
                InlineKeyboardButton("$25", callback_data="limit_bet_25"),
                InlineKeyboardButton("$50", callback_data="limit_bet_50"),
            ],
            [
                InlineKeyboardButton("$100", callback_data="limit_bet_100"),
                InlineKeyboardButton("$250", callback_data="limit_bet_250"),
                InlineKeyboardButton("$500", callback_data="limit_bet_500"),
            ],
            [
                InlineKeyboardButton(
                    f"⚙️ Default (${default_bet:.0f})",
                    callback_data=f"limit_bet_{default_bet}",
                ),
                InlineKeyboardButton("✏️ Custom", callback_data="limit_bet_custom"),
            ],
            [InlineKeyboardButton("« Cancel", callback_data=f"market_{market_id}")],
        ]

        await message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )

        return ConversationHandler.END

    except ValueError:
        await message.reply_text(
            "❌ Invalid price. Please enter a number.\n\n" "Example: 0.75",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Cancel", callback_data="start")]]
            ),
        )
        return AWAITING_LIMIT_PRICE


async def handle_limit_bet_amount(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle limit order bet amount selection."""
    query = update.callback_query

    if query.data == "limit_bet_custom":
        await query.message.edit_text(
            "✏️ Enter your bet amount in USDT:\n\n" "Example: 75.50",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Cancel", callback_data="start")]]
            ),
        )
        context.user_data["awaiting_limit_custom_amount"] = True
        return AWAITING_BET_AMOUNT

    # Extract amount
    amount = float(query.data.split("_")[2])

    # Get context
    market_id = context.user_data.get(USER_DATA_MARKET)
    side = context.user_data.get(USER_DATA_SIDE)
    price = context.user_data.get("limit_price")
    settings = get_user_settings(context)

    # Show confirmation
    await show_limit_order_confirmation(update, context, market_id, side, amount, price)

    return ConversationHandler.END


async def handle_custom_limit_amount(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle custom limit order amount input."""
    message = update.message

    try:
        # Parse the amount
        amount = float(message.text.strip())

        # Validate amount
        if amount <= 0:
            await message.reply_text(
                "❌ Amount must be greater than 0.\n\nPlease enter a valid amount:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Cancel", callback_data="start")]]
                ),
            )
            return AWAITING_BET_AMOUNT

        if amount > 10000:
            await message.reply_text(
                "❌ Amount too large (max: $10,000).\n\nPlease enter a valid amount:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Cancel", callback_data="start")]]
                ),
            )
            return AWAITING_BET_AMOUNT

        # Get context
        market_id = context.user_data.get(USER_DATA_MARKET)
        side = context.user_data.get(USER_DATA_SIDE)
        price = context.user_data.get("limit_price")

        # Show confirmation
        await show_limit_order_confirmation(
            update, context, market_id, side, amount, price
        )

        return ConversationHandler.END

    except ValueError:
        await message.reply_text(
            "❌ Invalid amount. Please enter a number.\n\n" "Example: 75.50",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Cancel", callback_data="start")]]
            ),
        )
        return AWAITING_BET_AMOUNT


async def show_limit_order_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    market_id: int,
    side: str,
    amount: float,
    price: float,
) -> None:
    """Show limit order confirmation."""
    query = update.callback_query
    message = update.message

    try:
        client = PolymarketClient()
        market = client.get_market(market_id)

        # Calculate estimated shares
        estimated_shares = amount / price

        text = f"📝 <b>Confirm Limit Order</b>\n\n"
        text += f"<b>Market:</b> {market.marketTitle[:50]}\n"
        text += f"<b>Position:</b> {side}\n"
        text += f"<b>Amount:</b> ${amount:.2f} USDT\n"
        text += f"<b>Limit Price:</b> {format_price(price)} ({price*100:.1f}%)\n"
        text += f"<b>Est. Shares:</b> ~{estimated_shares:.0f}\n\n"
        text += (
            f"⏳ Your order will execute when market reaches {format_price(price)}\n\n"
        )
        text += f"Confirm to place limit order:"

        # Store for execution
        context.user_data["bet_amount"] = amount
        context.user_data["limit_price"] = price

        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data="execute_limit_order"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"market_{market_id}"),
            ],
        ]

        if query:
            await query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML,
            )

    except Exception as e:
        logger.error(f"Error showing limit order confirmation: {e}")
        error_text = "❌ Error preparing limit order. Please try again."
        keyboard = get_main_menu_keyboard()

        if query:
            await query.message.edit_text(error_text, reply_markup=keyboard)
        else:
            await message.reply_text(error_text, reply_markup=keyboard)


async def execute_limit_order(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Execute the limit order."""
    query = update.callback_query

    # Get from context
    market_id = context.user_data.get(USER_DATA_MARKET)
    outcome_index = context.user_data.get("outcome_index", 0)
    outcome_label = context.user_data.get("outcome_label", "Unknown")
    amount = context.user_data.get("bet_amount")
    price = context.user_data.get("limit_price")

    # Show processing message
    processing_text = f"⏳ <b>Processing Limit Order...</b>\n\n"
    processing_text += f"Position: {outcome_label}\n"
    processing_text += f"Amount: ${amount:.2f} USDT\n"
    processing_text += f"Limit Price: {format_price(price)}\n\n"
    processing_text += f"Please wait..."

    await query.message.edit_text(processing_text, parse_mode=ParseMode.HTML)

    try:
        # Get user's Polymarket client
        telegram_id = query.from_user.id
        client = get_user_polymarket_client(telegram_id)
        if not client:
            await query.message.edit_text(
                "❌ <b>No wallet found</b>\n\nUse /create_wallet or /import_wallet first.",
                parse_mode=ParseMode.HTML,
            )
            return

        market = client.get_market(market_id)

        # Get token ID by index
        if outcome_index < len(market.tokenIds):
            token_id = market.tokenIds[outcome_index]
        else:
            await query.message.edit_text(
                "❌ Invalid outcome selection.",
                parse_mode=ParseMode.HTML,
            )
            return

        # Create limit order
        from utils.polymarket_client import PlaceOrderDataInput, OrderSide, OrderType

        order = PlaceOrderDataInput(
            marketId=market_id,
            tokenId=token_id,
            side=OrderSide.BUY,
            orderType=OrderType.LIMIT_ORDER,
            price=str(price),  # Important: price as string for limit orders
            makerAmountInQuoteToken=str(amount),
        )

        result = client.place_order(order, check_approval=True)

        # Success message
        success_text = f"✅ <b>Limit Order Placed!</b>\n\n"
        success_text += f"Position: {outcome_label}\n"
        success_text += f"Amount: ${amount:.2f} USDT\n"
        success_text += f"Limit Price: {format_price(price)}\n"
        success_text += f"Status: ⏳ Pending\n\n"
        success_text += (
            f"Your order will execute when market reaches {format_price(price)}"
        )

        keyboard = [
            [InlineKeyboardButton("📊 View Markets", callback_data="markets")],
            [InlineKeyboardButton("💼 View Positions", callback_data="positions")],
            [InlineKeyboardButton("« Main Menu", callback_data="start")],
        ]

        await query.message.edit_text(
            success_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )

        # Clear context
        context.user_data.pop("limit_price", None)
        context.user_data.pop("order_type", None)

    except Exception as e:
        logger.error(f"Error executing limit order: {e}")
        error_text = f"❌ <b>Limit Order Failed</b>\n\n"
        error_text += f"Error: {str(e)}\n\n"
        error_text += f"Please try again or contact support."

        keyboard = [
            [InlineKeyboardButton("« Back", callback_data=f"market_{market_id}")],
        ]

        await query.message.edit_text(
            error_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )


async def initiate_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Initiate buy flow - show bet amount selection."""
    query = update.callback_query

    # Parse callback data: buy_{index}_{market_id} (e.g., buy_0_123, buy_1_123)
    parts = query.data.split("_")
    outcome_index = int(parts[1])  # 0, 1, 2, etc.
    market_id = int(parts[2])

    # Get market to determine outcome label
    client = PolymarketClient()
    market = client.get_market(market_id)

    # Determine outcome label based on market type
    if market.marketType == TopicType.BINARY:
        if outcome_index == 0:
            outcome_label = market.yesLabel or "YES"
        else:
            outcome_label = market.noLabel or "NO"
    else:  # CATEGORICAL
        # Get label from options or fallback
        if market.options and outcome_index < len(market.options):
            option = market.options[outcome_index]
            outcome_label = option.get("label") or option.get("name") or f"Option {outcome_index + 1}"
        else:
            outcome_label = f"Option {outcome_index + 1}"

    # Store in context
    context.user_data[USER_DATA_MARKET] = market_id
    context.user_data["outcome_index"] = outcome_index
    context.user_data["outcome_label"] = outcome_label

    # Get user settings
    settings = get_user_settings(context)
    default_bet = settings["default_bet"]

    text = f"💰 <b>Buy {outcome_label}</b>\n\n"
    text += f"Select bet amount (USDT):"

    keyboard = [
        [
            InlineKeyboardButton("$10", callback_data="bet_10"),
            InlineKeyboardButton("$25", callback_data="bet_25"),
            InlineKeyboardButton("$50", callback_data="bet_50"),
        ],
        [
            InlineKeyboardButton("$100", callback_data="bet_100"),
            InlineKeyboardButton("$250", callback_data="bet_250"),
            InlineKeyboardButton("$500", callback_data="bet_500"),
        ],
        [
            InlineKeyboardButton(
                f"⚙️ Default (${default_bet:.0f})", callback_data=f"bet_{default_bet}"
            ),
            InlineKeyboardButton("✏️ Custom", callback_data="bet_custom"),
        ],
        [
            InlineKeyboardButton("« Back", callback_data=f"market_{market_id}"),
        ],
    ]

    await query.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )

    return AWAITING_BET_AMOUNT


async def handle_bet_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle bet amount selection."""
    query = update.callback_query

    if query.data == "bet_custom":
        await query.message.edit_text(
            "✏️ Enter your bet amount in USDT:\n\n" "Example: 75.50",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Cancel", callback_data="start")]]
            ),
        )
        return AWAITING_BET_AMOUNT

    # Extract amount
    amount = float(query.data.split("_")[1])

    # Get context
    market_id = context.user_data.get(USER_DATA_MARKET)
    side = context.user_data.get(USER_DATA_SIDE)
    settings = get_user_settings(context)

    # Show confirmation or execute immediately
    if settings["confirm_trades"]:
        await show_trade_confirmation(update, context, market_id, side, amount)
    else:
        await execute_trade(update, context, market_id, side, amount)

    return ConversationHandler.END


async def handle_custom_bet_amount(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle custom bet amount text input."""
    message = update.message

    try:
        # Parse the amount
        amount = float(message.text.strip())

        # Validate amount
        if amount <= 0:
            await message.reply_text(
                "❌ Amount must be greater than 0.\n\nPlease enter a valid amount:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Cancel", callback_data="start")]]
                ),
            )
            return AWAITING_BET_AMOUNT

        if amount > 10000:
            await message.reply_text(
                "❌ Amount too large (max: $10,000).\n\nPlease enter a valid amount:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Cancel", callback_data="start")]]
                ),
            )
            return AWAITING_BET_AMOUNT

        # Get context
        market_id = context.user_data.get(USER_DATA_MARKET)
        side = context.user_data.get(USER_DATA_SIDE)
        settings = get_user_settings(context)

        # Show confirmation or execute immediately
        if settings["confirm_trades"]:
            await show_trade_confirmation(update, context, market_id, side, amount)
        else:
            await execute_trade(update, context, market_id, side, amount)

        return ConversationHandler.END

    except ValueError:
        await message.reply_text(
            "❌ Invalid amount. Please enter a number.\n\n" "Example: 75.50",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Cancel", callback_data="start")]]
            ),
        )
        return AWAITING_BET_AMOUNT


async def show_trade_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    market_id: int,
    side: str = None,  # Deprecated, kept for compatibility
    amount: float = None,
) -> None:
    """Show trade confirmation."""
    query = update.callback_query
    message = update.message

    # Get outcome data from context
    outcome_index = context.user_data.get("outcome_index", 0)
    outcome_label = context.user_data.get("outcome_label", side or "Unknown")

    try:
        client = PolymarketClient()
        market = client.get_market(market_id)

        # Get current price using outcome index
        if outcome_index < len(market.tokenIds):
            token_id = market.tokenIds[outcome_index]
            price = client.get_latest_price(token_id) or 0.50
        else:
            price = 0.50

        # Calculate estimated shares
        estimated_shares = amount / price if price > 0 else 0

        text = f"✅ <b>Confirm Trade</b>\n\n"
        text += f"<b>Market:</b> {market.marketTitle[:50]}\n"
        text += f"<b>Position:</b> {outcome_label}\n"
        text += f"<b>Amount:</b> ${amount:.2f} USDT\n"
        text += f"<b>Price:</b> {format_price(price)}\n"
        text += f"<b>Est. Shares:</b> ~{estimated_shares:.0f}\n\n"
        text += f"Confirm to execute trade:"

        # Store amount for execution
        context.user_data["bet_amount"] = amount

        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data="execute_trade"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"market_{market_id}"),
            ],
        ]

        if query:
            await query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML,
            )

    except Exception as e:
        logger.error(f"Error showing confirmation: {e}")
        error_text = "❌ Error preparing trade. Please try again."
        keyboard = get_main_menu_keyboard()

        if query:
            await query.message.edit_text(error_text, reply_markup=keyboard)
        else:
            await message.reply_text(error_text, reply_markup=keyboard)


async def execute_trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    market_id: int = None,
    outcome_index: int = None,
    outcome_label: str = None,
    amount: float = None,
    # Legacy parameters (deprecated, for backward compatibility)
    side: str = None,
) -> None:
    """Execute the trade."""
    query = update.callback_query
    if query:
        message = query.message
    else:
        message = update.message

    # Get from context if not provided
    if market_id is None:
        market_id = context.user_data.get(USER_DATA_MARKET)
    if outcome_index is None:
        outcome_index = context.user_data.get("outcome_index")
    if outcome_label is None:
        outcome_label = context.user_data.get("outcome_label", "Unknown")
    if amount is None:
        amount = context.user_data.get("bet_amount")

    # Legacy support: convert side to outcome_index
    if outcome_index is None and side is not None:
        outcome_index = 0 if side == "YES" else 1
        outcome_label = side

    # Show processing message
    processing_text = f"⏳ <b>Processing Trade...</b>\n\n"
    processing_text += f"Position: {outcome_label}\n"
    processing_text += f"Amount: ${amount:.2f} USDT\n\n"
    processing_text += f"Please wait..."

    if query:
        await message.edit_text(processing_text, parse_mode=ParseMode.HTML)
    else:
        sent_msg = await message.reply_text(processing_text, parse_mode=ParseMode.HTML)
        message = sent_msg

    try:
        # Get user's Polymarket client
        telegram_id = update.effective_user.id
        client = get_user_polymarket_client(telegram_id)
        if not client:
            error_text = "❌ <b>No wallet found</b>\n\nUse /create_wallet or /import_wallet first."
            if query:
                await message.edit_text(error_text, parse_mode=ParseMode.HTML)
            else:
                await message.reply_text(error_text, parse_mode=ParseMode.HTML)
            return

        # Execute buy using outcome index
        result = client.buy_outcome(
            market_id=market_id,
            outcome_index=outcome_index,
            amount_usdt=amount
        )

        # Record points for this trade
        try:
            from utils.referrals import ReferralManager
            from utils.storage import get_storage

            storage = get_storage()
            referral_mgr = ReferralManager(storage)

            # Get market title
            market = client.get_market(market_id)
            market_title = market.marketTitle if market else f"Market #{market_id}"

            # Record trade points (1 point per $1 + referral bonuses)
            referral_mgr.record_trade_points(
                telegram_id=telegram_id,
                volume_usdt=amount,
                market_id=market_id,
                market_title=market_title
            )

            # Get updated points for display
            points_data = referral_mgr.get_user_points(telegram_id)
            points_earned = amount  # 1 point per $1

        except Exception as e:
            logger.error(f"Error recording points: {e}")
            points_earned = None
            points_data = None

        # Success message
        success_text = f"✅ <b>Trade Executed!</b>\n\n"
        success_text += f"Position: {outcome_label}\n"
        success_text += f"Amount: ${amount:.2f} USDT\n"
        success_text += f"Status: ✅ Confirmed\n\n"

        # Add points info if available
        if points_earned:
            success_text += f"⭐ Points Earned: +{points_earned:.0f}\n"
            if points_data:
                success_text += f"💎 Total Points: {points_data['total_points']:,.0f}\n\n"
            else:
                success_text += f"\n"

        success_text += f"Check your positions to view details."

        keyboard = [
            [
                InlineKeyboardButton("📊 View Positions", callback_data="positions"),
                InlineKeyboardButton("🎴 Share Card", callback_data="generate_card"),
            ],
            [
                InlineKeyboardButton("« Main Menu", callback_data="start"),
            ],
        ]

        await message.edit_text(
            success_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )

    except Exception as e:
        logger.error(f"Error executing trade: {e}")
        error_text = f"❌ <b>Trade Failed</b>\n\n"
        error_text += f"Error: {str(e)}\n\n"
        error_text += f"Please check your balance and try again."

        await message.edit_text(
            error_text, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML
        )


# ============================================================================
# POSITIONS
# ============================================================================


async def show_positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's positions."""
    query = update.callback_query

    try:
        # Get user's Polymarket client for EOA wallet trading
        telegram_id = query.from_user.id
        client = get_user_polymarket_client(telegram_id)

        if not client:
            await query.message.edit_text(
                "❌ <b>No wallet found</b>\n\nPlease create a wallet using /create_wallet first.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_keyboard(),
            )
            return

        positions = client.get_my_positions()

        if not positions:
            text = "💼 <b>Your Positions</b>\n\n"
            text += "You don't have any open positions yet.\n\n"
            text += "Browse markets to start trading!"

            keyboard = [
                [InlineKeyboardButton("📊 Browse Markets", callback_data="markets")],
                [InlineKeyboardButton("« Back", callback_data="start")],
            ]

            await query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML,
            )
            return

        # Calculate total PnL
        total_pnl = sum(p.unrealizedPnl + p.realizedPnl for p in positions)
        total_value = sum(p.value for p in positions)

        text = f"💼 <b>Your Positions</b>\n\n"
        text += f"Total Value: <b>${total_value:,.2f}</b>\n"
        text += (
            f"Total PnL: <b>{format_pnl(total_pnl)}</b> {get_pnl_emoji(total_pnl)}\n\n"
        )

        keyboard = []

        for i, pos in enumerate(positions[:6], 1):  # Show top 6
            # Truncate market name
            market_name = pos.marketTitle
            if len(market_name) > 30:
                market_name = market_name[:27] + "..."

            pnl = pos.unrealizedPnl + pos.realizedPnl
            pnl_str = format_pnl(pnl)
            emoji = get_position_emoji(pos.tokenName, i)

            text += f"{i}. {emoji} {pos.tokenName} - {market_name}\n"
            text += f"   {pnl_str} | {pos.shares:.0f} shares @ {format_price(pos.avgPrice)}\n\n"

            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"{i}. {emoji} {pos.tokenName} - {market_name} ({pnl_str})",
                        callback_data=f"position_{pos.marketId}_{pos.tokenId}",
                    )
                ]
            )

        keyboard.extend(
            [
                [InlineKeyboardButton("🎴 Share All", callback_data="share_positions")],
                [InlineKeyboardButton("« Back", callback_data="start")],
            ]
        )

        await query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Error loading positions: {e}")
        await query.message.edit_text(
            "❌ Error loading positions. Please try again.",
            reply_markup=get_main_menu_keyboard(),
        )


async def show_position_details(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show detailed position view with sell options."""
    query = update.callback_query

    # Parse callback data
    parts = query.data.split("_")
    market_id = int(parts[1])
    token_id = parts[2]

    try:
        # Get user's Polymarket client
        telegram_id = query.from_user.id
        client = get_user_polymarket_client(telegram_id)
        if not client:
            await query.message.edit_text(
                "❌ <b>No wallet found</b>\n\nUse /create_wallet or /import_wallet first.",
                parse_mode=ParseMode.HTML,
            )
            return

        positions = client.get_my_positions(market_id=market_id)

        # Find matching position
        position = next((p for p in positions if p.tokenId == token_id), None)

        if not position:
            await query.message.edit_text(
                "❌ Position not found.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Back", callback_data="positions")]]
                ),
            )
            return

        pnl = position.unrealizedPnl + position.realizedPnl
        pnl_pct = (
            (pnl / (position.shares * position.avgPrice)) * 100
            if position.shares > 0
            else 0
        )

        emoji = get_position_emoji(position.tokenName)

        text = f"{emoji} <b>{position.marketTitle}</b>\n\n"
        text += f"<b>Position:</b> {position.tokenName}\n"
        text += f"<b>Shares:</b> {position.shares:.0f}\n"
        text += f"<b>Avg Price:</b> {format_price(position.avgPrice)}\n"
        text += f"<b>Current:</b> {format_price(position.currentPrice)}\n"
        text += f"<b>Value:</b> ${position.value:.2f}\n\n"
        text += (
            f"<b>PnL:</b> {format_pnl(pnl)} ({pnl_pct:+.1f}%) {get_pnl_emoji(pnl)}\n\n"
        )
        text += "Select action:"

        # Store position info
        context.user_data["current_position"] = {
            "market_id": market_id,
            "token_id": token_id,
            "shares": position.shares,
        }

        keyboard = [
            [
                InlineKeyboardButton(
                    "💸 Sell 25%", callback_data=f"sell_25_{market_id}_{token_id}"
                ),
                InlineKeyboardButton(
                    "💸 Sell 50%", callback_data=f"sell_50_{market_id}_{token_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "💸 Sell 75%", callback_data=f"sell_75_{market_id}_{token_id}"
                ),
                InlineKeyboardButton(
                    "💸 Sell 100%", callback_data=f"sell_100_{market_id}_{token_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🎴 Share Card",
                    callback_data=f"share_position_{market_id}_{token_id}",
                ),
            ],
            [InlineKeyboardButton("« Back", callback_data="positions")],
        ]

        await query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Error loading position: {e}")
        await query.message.edit_text(
            "❌ Error loading position. Please try again.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Back", callback_data="positions")]]
            ),
        )


# ============================================================================
# SETTINGS
# ============================================================================


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show settings menu."""
    query = update.callback_query

    settings = get_user_settings(context)

    text = "⚙️ <b>Settings</b>\n\n"
    text += "<b>Quick Settings:</b>\n\n"

    # Build status text
    auto_reload_status = "🟢 ON" if settings["auto_reload"] else "🔴 OFF"
    confirm_status = "🟢 ON" if settings["confirm_trades"] else "🔴 OFF"
    pnl_status = "🟢 Show" if settings["show_pnl"] else "🔴 Hide"
    chart_status = "🟢 Show" if settings["show_charts"] else "🔴 Hide"

    text += f"Auto-Reload: {auto_reload_status}\n"
    text += f"Confirm Trades: {confirm_status}\n"
    text += f"PnL Display: {pnl_status}\n"
    text += f"Chart Previews: {chart_status}\n"

    keyboard = [
        [
            InlineKeyboardButton(
                f"Auto-Reload: {auto_reload_status}", callback_data="toggle_auto_reload"
            ),
        ],
        [
            InlineKeyboardButton(
                f"Confirm Trades: {confirm_status}", callback_data="toggle_confirm"
            ),
        ],
        [
            InlineKeyboardButton(
                f"PnL Display: {pnl_status}", callback_data="toggle_pnl"
            ),
        ],
        [
            InlineKeyboardButton(
                f"Charts: {chart_status}", callback_data="toggle_charts"
            ),
        ],
        [InlineKeyboardButton("« Back", callback_data="start")],
    ]

    await query.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )


async def toggle_setting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle a boolean setting."""
    query = update.callback_query

    settings = get_user_settings(context)

    # Map callback to setting key
    toggle_map = {
        "toggle_auto_reload": "auto_reload",
        "toggle_confirm": "confirm_trades",
        "toggle_pnl": "show_pnl",
        "toggle_charts": "show_charts",
    }

    setting_key = toggle_map.get(query.data)
    if setting_key:
        settings[setting_key] = not settings[setting_key]
        # Save to persistent storage
        telegram_id = query.from_user.id
        update_persistent_user_settings(telegram_id, settings)

    # Refresh settings menu
    await show_settings(update, context)


# ============================================================================
# TRADING CARDS
# ============================================================================


async def generate_position_card(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Generate and send trading card for a position."""
    query = update.callback_query

    # Parse position info
    parts = query.data.split("_")
    market_id = int(parts[2])
    token_id = parts[3]

    try:
        from telegram import Bot, User as TelegramUser

        # Get user's Polymarket client
        telegram_id = query.from_user.id
        client = get_user_polymarket_client(telegram_id)
        if not client:
            await query.message.reply_text(
                "❌ <b>No wallet found</b>\n\nUse /create_wallet or /import_wallet first.",
                parse_mode=ParseMode.HTML,
            )
            return

        positions = client.get_my_positions(market_id=market_id)
        position = next((p for p in positions if p.tokenId == token_id), None)

        if not position:
            await query.message.reply_text("❌ Position not found.")
            return

        # Create mock bot and user for card generation
        bot = context.bot
        user = update.effective_user

        # Generate card
        card_path = await generate_card_for_position(
            bot=bot, user=user, position=position
        )

        # Send as photo
        with open(card_path, "rb") as photo:
            caption = (
                f"🎴 Trading Card for {user.first_name}\n\n"
                f"{position.marketTitle}\n"
                f"PnL: {format_pnl(position.unrealizedPnl + position.realizedPnl)}"
            )

            await query.message.reply_photo(
                photo=photo,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Back", callback_data="positions")]]
                ),
            )

    except Exception as e:
        logger.error(f"Error generating card: {e}")
        await query.message.reply_text(
            "❌ Error generating card. Please try again.",
            reply_markup=get_main_menu_keyboard(),
        )


# ============================================================================
# WALLET MANAGEMENT
# ============================================================================


async def show_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show wallet information and management options."""
    query = update.callback_query
    if query:
        message = query.message
    else:
        message = update.message

    try:
        # Get user's EOA wallet
        telegram_id = update.effective_user.id
        account_mgr = get_user_account_manager(telegram_id)

        if account_mgr:
            wallet_address = account_mgr.get_address()
            balances = account_mgr.get_all_balances()

            text = f"💰 <b>Wallet</b>\n\n"
            text += f"<b>Address:</b>\n<code>{wallet_address}</code>\n\n"
            text += f"<b>Balances:</b>\n"
            text += f"• BNB: {balances['bnb']:.6f}\n"
            text += f"• USDT: ${balances['usdt']:.2f}\n\n"
            text += f"<i>BNB is used for gas fees</i>"

            keyboard = [
                [
                    InlineKeyboardButton("📤 Deposit", callback_data="wallet_deposit"),
                    InlineKeyboardButton("📥 Withdraw", callback_data="wallet_withdraw"),
                ],
                [InlineKeyboardButton("« Back", callback_data="start")],
            ]
        else:
            # Show wallet import/connect options
            text = f"💰 <b>Wallet</b>\n\n"
            text += f"No wallet connected.\n\n"
            text += f"To start trading, you need to connect a wallet or create a new one.\n\n"
            text += f"⚠️ <b>Security:</b> Your private key is stored securely and never shared."

            keyboard = [
                [
                    InlineKeyboardButton(
                        "🔑 Import Wallet", callback_data="wallet_import"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "➕ Create Wallet", callback_data="wallet_create"
                    )
                ],
                [InlineKeyboardButton("« Back", callback_data="start")],
            ]

        if query:
            await message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML,
            )

    except Exception as e:
        logger.error(f"Error showing wallet: {e}")
        error_text = "❌ Error loading wallet information."
        keyboard = [[InlineKeyboardButton("« Back", callback_data="start")]]

        if query:
            await message.edit_text(
                error_text, reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await message.reply_text(
                error_text, reply_markup=InlineKeyboardMarkup(keyboard)
            )


async def create_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a new wallet."""
    query = update.callback_query

    try:
        # Create wallet for this user
        telegram_id = query.from_user.id
        telegram_username = query.from_user.username
        account_info = create_user_wallet(
            telegram_id, telegram_username=telegram_username, testnet=False
        )

        text = f"✅ <b>Wallet Created!</b>\n\n"
        text += f"<b>Address:</b>\n<code>{account_info['address']}</code>\n\n"
        text += f"<b>⚠️ IMPORTANT - Save Your Private Key:</b>\n"
        text += f"<code>{account_info['private_key']}</code>\n\n"
        text += f"⚠️ Never share this key with anyone!\n"
        text += f"⚠️ Anyone with this key can access your funds!\n"
        text += f"⚠️ Store it somewhere safe!\n\n"
        text += f"<i>This is the ONLY time your private key will be shown!</i>\n"
        text += f"<i>You'll need to deposit USDT and BNB to start trading.</i>"

        keyboard = [
            [InlineKeyboardButton("💰 View Wallet", callback_data="wallet")],
            [InlineKeyboardButton("« Main Menu", callback_data="start")],
        ]

        await query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Error creating wallet: {e}")
        await query.message.edit_text(
            "❌ Error creating wallet. Please try again.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Back", callback_data="wallet")]]
            ),
        )


async def initiate_wallet_import(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Initiate wallet import with security warnings."""
    query = update.callback_query

    text = f"🔑 <b>Import Wallet</b>\n\n"
    text += f"⚠️ <b>SECURITY WARNING:</b>\n\n"
    text += f"🔒 Never share your private key with anyone\n"
    text += f"🔒 This bot does NOT store your private key on servers\n"
    text += f"🔒 Your key is only stored locally in your session\n"
    text += f"🔒 Make sure you trust this bot before proceeding\n\n"
    text += f"Enter your private key (with or without 0x prefix):\n\n"
    text += f"<i>Example: 0xabc123... or abc123...</i>\n\n"
    text += f"⚠️ <b>WARNING:</b> Only import wallets you control!"

    keyboard = [[InlineKeyboardButton("« Cancel", callback_data="wallet")]]

    await query.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )

    return AWAITING_WALLET_IMPORT


async def handle_wallet_import(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle private key input and import wallet."""
    message = update.message

    try:
        # Get private key from message
        private_key = message.text.strip()

        # Delete the message immediately for security
        try:
            await message.delete()
        except Exception:
            pass  # Message may already be deleted

        # Validate private key format (basic check)
        if not private_key:
            await message.reply_text(
                "❌ Private key cannot be empty.\n\nPlease enter your private key:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Cancel", callback_data="wallet")]]
                ),
            )
            return AWAITING_WALLET_IMPORT

        # Remove 0x prefix if present
        if private_key.startswith("0x") or private_key.startswith("0X"):
            private_key = private_key[2:]

        # Basic validation: should be 64 hex characters
        if len(private_key) != 64:
            await message.reply_text(
                "❌ Invalid private key length.\n\n"
                "Private key must be 64 hex characters (with or without 0x prefix).\n\n"
                "Please try again:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Cancel", callback_data="wallet")]]
                ),
            )
            return AWAITING_WALLET_IMPORT

        # Check if it's valid hex
        try:
            int(private_key, 16)
        except ValueError:
            await message.reply_text(
                "❌ Invalid private key format.\n\n"
                "Private key must contain only hex characters (0-9, a-f).\n\n"
                "Please try again:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Cancel", callback_data="wallet")]]
                ),
            )
            return AWAITING_WALLET_IMPORT

        # Import wallet for this user
        telegram_id = update.effective_user.id
        telegram_username = update.effective_user.username
        account_info = import_user_wallet(
            telegram_id,
            "0x" + private_key,
            telegram_username=telegram_username,
            testnet=False,
        )

        # Get balances to confirm wallet works
        account_mgr = get_user_account_manager(telegram_id)
        balances = account_mgr.get_all_balances()

        # Success message
        text = f"✅ <b>Wallet Imported Successfully!</b>\n\n"
        text += f"<b>Address:</b>\n<code>{account_info['address']}</code>\n\n"
        text += f"<b>Balances:</b>\n"
        text += f"• BNB: {balances['bnb']:.6f}\n"
        text += f"• USDT: ${balances['usdt']:.2f}\n\n"
        text += f"🔒 Your private key is encrypted and stored securely.\n\n"
        text += f"<i>You can now start trading!</i>"

        keyboard = [
            [InlineKeyboardButton("💰 View Wallet", callback_data="wallet")],
            [InlineKeyboardButton("📊 Browse Markets", callback_data="markets")],
            [InlineKeyboardButton("« Main Menu", callback_data="start")],
        ]

        await message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error importing wallet: {e}")

        error_text = f"❌ <b>Wallet Import Failed</b>\n\n"

        # Provide specific error messages
        error_str = str(e).lower()
        if "invalid" in error_str or "format" in error_str:
            error_text += f"Invalid private key format.\n\n"
            error_text += f"Please check your private key and try again."
        elif "connect" in error_str or "rpc" in error_str:
            error_text += f"Cannot connect to blockchain.\n\n"
            error_text += f"Please check your internet connection and try again."
        else:
            error_text += f"Error: {str(e)}\n\n"
            error_text += f"Please verify your private key and try again."

        keyboard = [
            [InlineKeyboardButton("🔄 Try Again", callback_data="wallet_import")],
            [InlineKeyboardButton("« Back", callback_data="wallet")],
        ]

        await message.reply_text(
            error_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )

        return ConversationHandler.END


async def show_deposit_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show deposit information for BSC."""
    query = update.callback_query

    # Get user's EOA wallet address
    telegram_id = update.effective_user.id
    account_mgr = get_user_account_manager(telegram_id)
    wallet_address = account_mgr.get_address() if account_mgr else None

    if not wallet_address:
        await query.message.edit_text(
            "❌ No wallet connected.\n\nPlease create a wallet using /create_wallet first.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Back", callback_data="wallet")]]
            ),
        )
        return

    text = f"📤 <b>Deposit Funds</b>\n\n"
    text += f"<b>Your Wallet Address:</b>\n"
    text += f"<code>{wallet_address}</code>\n\n"

    text += f"<b>Network:</b>\n"
    text += f"• Polygon (BSC) - BEP20\n\n"

    text += f"<b>✅ Accepted Tokens:</b>\n"
    text += f"• <b>USDT</b> - For trading\n"
    text += f"• <b>BNB</b> - For gas fees\n\n"

    text += f"<b>⚠️ Important:</b>\n"
    text += f"• Only send on <b>Polygon (BSC)</b>\n"
    text += f"• Need ~0.01 BNB for gas fees\n"
    text += f"• Double check network before sending\n\n"

    text += f"<b>⛔ DO NOT Send:</b>\n"
    text += f"• Tokens on Ethereum/Base/other chains\n"
    text += f"• Other tokens (USDC, BUSD, etc.)\n"
    text += f"• NFTs or non-standard tokens\n\n"

    text += f"<i>💡 Tap address above to copy</i>"

    keyboard = [
        [InlineKeyboardButton("« Back", callback_data="wallet")],
    ]

    await query.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )


# ============================================================================
# WALLET WITHDRAWAL
# ============================================================================


async def show_withdrawal_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show withdrawal asset selection menu."""
    query = update.callback_query

    # Get user's wallet and balances
    telegram_id = update.effective_user.id
    account_mgr = get_user_account_manager(telegram_id)

    if not account_mgr:
        await query.message.edit_text(
            "❌ No wallet connected.\n\nPlease create a wallet using /create_wallet first.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Back", callback_data="wallet")]]
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    balances = account_mgr.get_all_balances()

    text = f"📥 <b>Withdraw Funds</b>\n\n"
    text += f"<b>Available Balances:</b>\n"
    text += f"• BNB: {balances['bnb']:.6f}\n"
    text += f"• USDT: ${balances['usdt']:.2f}\n\n"
    text += f"Select asset to withdraw:"

    keyboard = [
        [InlineKeyboardButton(f"BNB ({balances['bnb']:.4f} available)", callback_data="withdraw_bnb")],
        [InlineKeyboardButton(f"USDT (${balances['usdt']:.2f} available)", callback_data="withdraw_usdt")],
        [InlineKeyboardButton("« Back", callback_data="wallet")],
    ]

    await query.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )


async def initiate_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start withdrawal process - ask for recipient address."""
    query = update.callback_query

    # Parse asset from callback_data: withdraw_bnb or withdraw_usdt
    asset = query.data.split("_")[1].upper()
    context.user_data["withdrawal_asset"] = asset

    text = f"📥 <b>Withdraw {asset}</b>\n\n"
    text += f"<b>Step 1/2:</b> Enter recipient address\n\n"
    text += f"Please enter the Polygon (BSC) address where you want to send {asset}.\n\n"
    text += f"<b>Example:</b>\n"
    text += f"<code>0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb</code>\n\n"
    text += f"⚠️ <b>Important:</b> Double-check the address. Transactions cannot be reversed!"

    keyboard = [[InlineKeyboardButton("« Cancel", callback_data="wallet")]]

    await query.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )

    return AWAITING_WITHDRAWAL_ADDRESS


async def handle_withdrawal_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process withdrawal address and ask for amount."""
    message = update.message
    address = message.text.strip()

    # Validate address format (basic validation)
    if not address.startswith("0x") or len(address) != 42:
        await message.reply_text(
            "❌ <b>Invalid Address</b>\n\n"
            "Please enter a valid Polygon address starting with 0x.\n\n"
            "Example: <code>0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb</code>",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Cancel", callback_data="wallet")]]
            ),
            parse_mode=ParseMode.HTML,
        )
        return AWAITING_WITHDRAWAL_ADDRESS

    # Store address
    context.user_data["withdrawal_address"] = address
    asset = context.user_data.get("withdrawal_asset", "BNB")

    # Get balance
    telegram_id = update.effective_user.id
    account_mgr = get_user_account_manager(telegram_id)
    balances = account_mgr.get_all_balances()

    if asset == "BNB":
        available = balances['bnb']
        # Reserve some BNB for gas
        max_amount = max(0, available - 0.001)
    else:  # USDT
        available = balances['usdt']
        max_amount = available

    text = f"📥 <b>Withdraw {asset}</b>\n\n"
    text += f"<b>Step 2/2:</b> Enter amount\n\n"
    text += f"<b>Recipient:</b>\n<code>{address}</code>\n\n"
    text += f"<b>Available:</b> "
    if asset == "BNB":
        text += f"{available:.6f} {asset}\n"
        text += f"<b>Max withdraw:</b> {max_amount:.6f} {asset}\n"
        text += f"<i>(0.001 BNB reserved for gas)</i>\n\n"
    else:
        text += f"${available:.2f}\n\n"

    text += f"Enter amount to withdraw:"

    keyboard = [[InlineKeyboardButton("« Cancel", callback_data="wallet")]]

    await message.reply_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )

    return AWAITING_WITHDRAWAL_AMOUNT


async def handle_withdrawal_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process withdrawal amount and show confirmation."""
    message = update.message
    amount_str = message.text.strip()

    try:
        amount = float(amount_str)
    except ValueError:
        await message.reply_text(
            "❌ Invalid amount. Please enter a number.\n\n"
            "Example: 0.5",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Cancel", callback_data="wallet")]]
            ),
            parse_mode=ParseMode.HTML,
        )
        return AWAITING_WITHDRAWAL_AMOUNT

    if amount <= 0:
        await message.reply_text(
            "❌ Amount must be greater than 0.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Cancel", callback_data="wallet")]]
            ),
            parse_mode=ParseMode.HTML,
        )
        return AWAITING_WITHDRAWAL_AMOUNT

    # Get balance and validate
    telegram_id = update.effective_user.id
    account_mgr = get_user_account_manager(telegram_id)
    balances = account_mgr.get_all_balances()

    asset = context.user_data.get("withdrawal_asset", "BNB")
    address = context.user_data.get("withdrawal_address")

    if asset == "BNB":
        available = balances['bnb']
        # Need to keep some for gas
        if amount > available - 0.001:
            await message.reply_text(
                f"❌ <b>Insufficient Balance</b>\n\n"
                f"Available: {available:.6f} BNB\n"
                f"Maximum: {available - 0.001:.6f} BNB\n"
                f"(0.001 BNB reserved for gas)\n\n"
                f"Please enter a lower amount.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Cancel", callback_data="wallet")]]
                ),
                parse_mode=ParseMode.HTML,
            )
            return AWAITING_WITHDRAWAL_AMOUNT
    else:  # USDT
        available = balances['usdt']
        if amount > available:
            await message.reply_text(
                f"❌ <b>Insufficient Balance</b>\n\n"
                f"Available: ${available:.2f}\n\n"
                f"Please enter a lower amount.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Cancel", callback_data="wallet")]]
                ),
                parse_mode=ParseMode.HTML,
            )
            return AWAITING_WITHDRAWAL_AMOUNT

    # Store amount
    context.user_data["withdrawal_amount"] = amount

    # Show confirmation
    text = f"⚠️ <b>Confirm Withdrawal</b>\n\n"
    text += f"<b>Asset:</b> {asset}\n"
    text += f"<b>Amount:</b> "
    if asset == "BNB":
        text += f"{amount:.6f} {asset}\n"
    else:
        text += f"${amount:.2f}\n"
    text += f"\n<b>To Address:</b>\n<code>{address}</code>\n\n"
    text += f"⚠️ <b>Warning:</b> This transaction cannot be reversed!\n\n"
    text += f"Please confirm you want to proceed."

    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data="execute_withdrawal"),
            InlineKeyboardButton("❌ Cancel", callback_data="wallet"),
        ],
    ]

    await message.reply_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )

    return ConversationHandler.END


async def execute_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute the withdrawal transaction."""
    query = update.callback_query

    asset = context.user_data.get("withdrawal_asset")
    address = context.user_data.get("withdrawal_address")
    amount = context.user_data.get("withdrawal_amount")

    if not all([asset, address, amount]):
        await query.message.edit_text(
            "❌ Withdrawal session expired. Please start over.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Back", callback_data="wallet")]]
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    # Show processing message
    processing_text = f"⏳ <b>Processing Withdrawal...</b>\n\n"
    processing_text += f"Sending {amount:.6f if asset == 'BNB' else amount:.2f} {asset} to:\n"
    processing_text += f"<code>{address}</code>\n\n"
    processing_text += f"Please wait..."

    await query.message.edit_text(processing_text, parse_mode=ParseMode.HTML)

    try:
        # Get user's account manager
        telegram_id = query.from_user.id
        account_mgr = get_user_account_manager(telegram_id)

        if not account_mgr:
            raise Exception("Wallet not found")

        # Execute withdrawal
        if asset == "BNB":
            tx_hash = account_mgr.send_bnb(address, amount)
        else:  # USDT
            tx_hash = account_mgr.send_usdt(address, amount)

        # Success message
        success_text = f"✅ <b>Withdrawal Successful!</b>\n\n"
        success_text += f"<b>Asset:</b> {asset}\n"
        success_text += f"<b>Amount:</b> "
        if asset == "BNB":
            success_text += f"{amount:.6f} {asset}\n"
        else:
            success_text += f"${amount:.2f}\n"
        success_text += f"\n<b>To:</b>\n<code>{address}</code>\n\n"
        success_text += f"<b>Transaction:</b>\n<code>{tx_hash}</code>\n\n"
        success_text += f"<a href='https://bscscan.com/tx/{tx_hash}'>View on BscScan</a>"

        keyboard = [
            [InlineKeyboardButton("💰 View Wallet", callback_data="wallet")],
            [InlineKeyboardButton("« Main Menu", callback_data="start")],
        ]

        await query.message.edit_text(
            success_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )

        # Clear withdrawal data
        context.user_data.pop("withdrawal_asset", None)
        context.user_data.pop("withdrawal_address", None)
        context.user_data.pop("withdrawal_amount", None)

    except Exception as e:
        logger.error(f"Withdrawal failed: {e}")
        error_text = f"❌ <b>Withdrawal Failed</b>\n\n"
        error_text += f"Error: {str(e)}\n\n"
        error_text += f"Please try again or contact support if the issue persists."

        keyboard = [
            [InlineKeyboardButton("💰 Back to Wallet", callback_data="wallet")],
            [InlineKeyboardButton("« Main Menu", callback_data="start")],
        ]

        await query.message.edit_text(
            error_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )


# ============================================================================
# POSITION SELLING
# ============================================================================


async def sell_position(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sell a percentage of a position."""
    query = update.callback_query

    # Parse sell data: sell_{percent}_{market_id}_{token_id}
    parts = query.data.split("_")
    percent = int(parts[1])
    market_id = int(parts[2])
    token_id = parts[3]

    try:
        # Get user's Polymarket client
        telegram_id = query.from_user.id
        client = get_user_polymarket_client(telegram_id)
        if not client:
            await query.message.edit_text(
                "❌ <b>No wallet found</b>\n\nUse /create_wallet or /import_wallet first.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Back", callback_data="positions")]]
                ),
                parse_mode=ParseMode.HTML,
            )
            return

        positions = client.get_my_positions(market_id=market_id)
        position = next((p for p in positions if p.tokenId == token_id), None)

        if not position:
            await query.message.edit_text(
                "❌ Position not found.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Back", callback_data="positions")]]
                ),
            )
            return

        # Calculate sell amount
        sell_amount = position.shares * (percent / 100.0)

        # Show confirmation
        text = f"💸 <b>Confirm Sell</b>\n\n"
        text += f"<b>Market:</b> {position.marketTitle[:50]}\n"
        text += f"<b>Position:</b> {position.tokenName}\n"
        text += f"<b>Selling:</b> {percent}% ({sell_amount:.2f} shares)\n"
        text += f"<b>Current Price:</b> {format_price(position.currentPrice)}\n"
        text += f"<b>Est. Proceeds:</b> ${sell_amount * position.currentPrice:.2f}\n\n"
        text += f"Confirm to sell:"

        # Store sell info
        context.user_data["sell_position"] = {
            "position": position,
            "percent": percent,
            "amount": sell_amount,
        }

        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"execute_sell"),
                InlineKeyboardButton(
                    "❌ Cancel", callback_data=f"position_{market_id}_{token_id}"
                ),
            ],
        ]

        await query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Error preparing sell: {e}")
        await query.message.edit_text(
            "❌ Error preparing sell order. Please try again.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Back", callback_data="positions")]]
            ),
        )


async def execute_sell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute the sell order."""
    query = update.callback_query

    sell_info = context.user_data.get("sell_position")

    if not sell_info:
        await query.message.edit_text(
            "❌ Sell information not found.", reply_markup=get_main_menu_keyboard()
        )
        return

    position = sell_info["position"]
    amount = sell_info["amount"]
    percent = sell_info["percent"]

    # Show processing message
    processing_text = f"⏳ <b>Processing Sell...</b>\n\n"
    processing_text += f"Selling {percent}% of {position.tokenName} position\n"
    processing_text += f"Amount: {amount:.2f} shares\n\n"
    processing_text += f"Please wait..."

    await query.message.edit_text(processing_text, parse_mode=ParseMode.HTML)

    try:
        # Get user's Polymarket client
        telegram_id = query.from_user.id
        client = get_user_polymarket_client(telegram_id)
        if not client:
            await query.message.edit_text(
                "❌ <b>No wallet found</b>\n\nUse /create_wallet or /import_wallet first.",
                parse_mode=ParseMode.HTML,
            )
            return

        # Execute sell using sell_position convenience method
        result = client.sell_position(
            position=position, amount=amount, price=None  # Market order
        )

        # Success message
        estimated_proceeds = amount * position.currentPrice
        success_text = f"✅ <b>Sell Order Executed!</b>\n\n"
        success_text += f"Position: {position.tokenName}\n"
        success_text += f"Sold: {percent}% ({amount:.2f} shares)\n"
        success_text += f"Est. Proceeds: ${estimated_proceeds:.2f}\n"
        success_text += f"Status: ✅ Confirmed\n\n"
        success_text += f"Check your positions to view updated details."

        keyboard = [
            [InlineKeyboardButton("💼 View Positions", callback_data="positions")],
            [InlineKeyboardButton("« Main Menu", callback_data="start")],
        ]

        await query.message.edit_text(
            success_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )

        # Clear sell info
        context.user_data.pop("sell_position", None)

    except Exception as e:
        logger.error(f"Error executing sell: {e}")
        error_text = f"❌ <b>Sell Failed</b>\n\n"
        error_text += f"Error: {str(e)}\n\n"
        error_text += f"Please try again or contact support."

        keyboard = [
            [InlineKeyboardButton("« Back", callback_data="positions")],
        ]

        await query.message.edit_text(
            error_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )


# ============================================================================
# PNL HISTORY
# ============================================================================


async def show_pnl_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show PnL history with timeframe selection."""
    query = update.callback_query
    if query:
        message = query.message
    else:
        message = update.message

    text = f"📈 <b>PnL History</b>\n\n"
    text += f"Select a timeframe to view your performance chart:"

    keyboard = [
        [
            InlineKeyboardButton("1D", callback_data="pnl_1d"),
            InlineKeyboardButton("1W", callback_data="pnl_1w"),
        ],
        [
            InlineKeyboardButton("1M", callback_data="pnl_1m"),
            InlineKeyboardButton("ALL", callback_data="pnl_all"),
        ],
        [InlineKeyboardButton("« Back", callback_data="start")],
    ]

    if query:
        await message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )
    else:
        await message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )


async def generate_pnl_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send PnL history card."""
    query = update.callback_query

    # Parse timeframe
    timeframe = query.data.split("_")[1].upper()

    try:
        from datetime import datetime, timedelta
        import random

        # Get user info
        user = update.effective_user

        # Get user's Polymarket client
        telegram_id = user.id
        client = get_user_polymarket_client(telegram_id)
        if not client:
            await query.message.reply_text(
                "❌ <b>No wallet found</b>\n\nUse /create_wallet or /import_wallet first.",
                parse_mode=ParseMode.HTML,
            )
            return

        # Get current positions for PnL calculation
        pnl_data = client.get_my_pnl()

        # Generate mock historical data based on timeframe
        # In production, this would fetch actual trade history
        now = datetime.now()
        if timeframe == "1D":
            days = 1
            points = 24  # Hourly
        elif timeframe == "1W":
            days = 7
            points = 7  # Daily
        elif timeframe == "1M":
            days = 30
            points = 30  # Daily
        else:  # ALL
            days = 90
            points = 30  # Every 3 days

        # Generate mock PnL history
        history_data = []
        current_pnl = pnl_data["total_pnl"]
        base_pnl = current_pnl * 0.5  # Start at 50% of current

        for i in range(points):
            timestamp = int(
                (now - timedelta(days=days - (i * days / points))).timestamp()
            )
            # Simulate growth trend
            pnl = base_pnl + (current_pnl - base_pnl) * (i / points)
            # Add some noise
            pnl += random.uniform(-abs(current_pnl * 0.1), abs(current_pnl * 0.1))
            history_data.append((timestamp, pnl))

        # Create PnL card
        card = PnLHistoryCard(
            username=user.first_name or user.username or "Trader",
            timeframe=timeframe,
            history_data=history_data,
            user_icon_path=None,  # Could download profile pic here
        )

        # Save card
        output_dir = Path("cards")
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / f"pnl_{user.id}_{timeframe}.png"
        card.save(str(output_path))

        # Send as photo
        with open(output_path, "rb") as photo:
            caption = (
                f"📈 PnL History - {timeframe}\n\n"
                f"Total PnL: {format_pnl(current_pnl)}\n"
                f"Period: {timeframe}"
            )

            await query.message.reply_photo(
                photo=photo,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("« Back", callback_data="pnl_history")]]
                ),
            )

    except Exception as e:
        logger.error(f"Error generating PnL card: {e}")
        await query.message.reply_text(
            "❌ Error generating PnL chart. Please try again.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("« Back", callback_data="pnl_history")]]
            ),
        )


# ============================================================================
# CALLBACK HANDLERS
# ============================================================================


async def button_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> Optional[int]:
    """Handle all button callbacks."""
    query = update.callback_query
    await query.answer()  # Acknowledge the callback query to remove loading state

    # Route to appropriate handler
    if query.data == "start" or query.data == "refresh_main":
        await start(update, context)

    elif query.data == "markets":
        await show_markets(update, context)

    elif query.data == "search_markets":
        return await initiate_search(update, context)

    elif query.data.startswith("searchres_"):
        logger.info(f"Callback received: {query.data}")
        await handle_search_result_click(update, context)

    elif query.data.startswith("catmarket_"):
        logger.info(f"Callback received: {query.data}")
        await show_categorical_outcomes(update, context)

    elif query.data.startswith("market_"):
        logger.info(f"Callback received: {query.data}")
        await show_market_details(update, context)

    elif query.data.startswith("option_"):
        await show_option_trading(update, context)

    elif query.data.startswith("buy_"):
        return await initiate_buy(update, context)

    elif query.data.startswith("limit_"):
        if query.data.startswith("limit_bet_"):
            return await handle_limit_bet_amount(update, context)
        else:
            return await initiate_limit_order(update, context)

    elif query.data.startswith("bet_"):
        return await handle_bet_amount(update, context)

    elif query.data == "execute_trade":
        await execute_trade(update, context)

    elif query.data == "execute_limit_order":
        await execute_limit_order(update, context)

    elif query.data == "positions":
        await show_positions(update, context)

    elif query.data.startswith("position_"):
        await show_position_details(update, context)

    elif query.data.startswith("share_position_"):
        await generate_position_card(update, context)

    elif query.data.startswith("sell_"):
        await sell_position(update, context)

    elif query.data == "execute_sell":
        await execute_sell(update, context)

    elif query.data == "wallet":
        await show_wallet(update, context)

    elif query.data == "wallet_create":
        await create_wallet(update, context)

    elif query.data == "wallet_import":
        return await initiate_wallet_import(update, context)

    elif query.data == "wallet_deposit":
        await show_deposit_info(update, context)

    elif query.data == "wallet_withdraw":
        await show_withdrawal_menu(update, context)

    elif query.data.startswith("withdraw_"):
        return await initiate_withdrawal(update, context)

    elif query.data == "execute_withdrawal":
        await execute_withdrawal(update, context)

    elif query.data == "pnl_history":
        await show_pnl_history(update, context)

    elif query.data.startswith("pnl_"):
        await generate_pnl_card(update, context)

    elif query.data == "settings":
        await show_settings(update, context)

    elif query.data.startswith("toggle_"):
        await toggle_setting(update, context)

    # Copytrading handlers
    elif query.data == "copytrading":
        await show_copytrading(update, context)

    elif query.data == "copy_add":
        return await initiate_copy_add(update, context)

    elif query.data.startswith("copy_toggle:"):
        await toggle_copy_subscription(update, context)

    elif query.data.startswith("copy_delete:"):
        await delete_copy_subscription(update, context)

    elif query.data.startswith("copy_scale:"):
        return await handle_copy_scale(update, context)

    elif query.data == "help":
        await show_help(update, context)

    elif query.data == "show_points":
        await show_points(update, context)

    elif query.data == "referrals":
        await show_referral(update, context)

    elif query.data == "change_referral_code":
        return await change_referral_code_prompt(update, context)

    elif query.data == "connect_safe":
        return await connect_safe_prompt(update, context)

    else:
        await query.answer("Feature coming soon!")

    return ConversationHandler.END


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help information."""
    query = update.callback_query
    if query:
        message = query.message
    else:
        message = update.message

    text = (
        "❓ <b>Help - Polymarket Trading Bot</b>\n\n"
        "<b>Available Commands:</b>\n"
        "/home - Launch the bot and display the main menu\n"
        "/help - Show information and available commands\n"
        "/setup - Guide for setting up your Safe wallet for Polymarket trading\n"
        "/markets - Browse all active prediction markets\n"
        "/search - Search for markets by keyword\n"
        "/positions - View your open positions\n"
        "/pnl_history - View your PnL over time\n"
        "/points - View your Polymarket points\n"
        "/referral - Get your unique code and view your referrals\n\n"
        "<b>Quick Guide:</b>\n"
        "1️⃣ Set up your wallet with /setup\n"
        "2️⃣ Browse markets with /markets or /search\n"
        "3️⃣ Choose an outcome on a market\n"
        "4️⃣ Select bet amount\n"
        "5️⃣ Confirm trade\n"
        "6️⃣ Earn points and refer friends!\n\n"
        "Need more help? Contact support or visit our docs."
    )

    keyboard = [[InlineKeyboardButton("« Back", callback_data="start")]]

    if query:
        await message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )
    else:
        await message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )


# ============================================================================
# POINTS AND REFERRAL SYSTEM
# ============================================================================


async def show_points(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's points and rewards."""
    query = update.callback_query
    message = query.message if query else update.message
    telegram_id = update.effective_user.id

    # Import referral manager
    from utils.referrals import ReferralManager
    from utils.storage import get_storage

    try:
        storage = get_storage()
        referral_mgr = ReferralManager(storage)

        # Get user's points data
        points_data = referral_mgr.get_user_points(telegram_id)
    except Exception as e:
        logger.error(f"Error in show_points for user {telegram_id}: {e}", exc_info=True)
        error_text = f"❌ Failed to load points data.\n\nError: {str(e)[:100]}"
        if query:
            await message.edit_text(error_text, parse_mode=ParseMode.HTML)
        else:
            await message.reply_text(error_text, parse_mode=ParseMode.HTML)
        return

    # Format text
    text = f"⭐ <b>Your Polymarket Points</b>\n\n"
    text += f"💎 <b>Total Points:</b> {points_data['total_points']:,.2f}\n"
    text += f"📊 <b>Trading Volume:</b> ${points_data['total_volume']:,.2f}\n\n"

    # Points breakdown
    trade_points = points_data['total_points'] - points_data['referrals_points']
    text += f"<b>Points Breakdown:</b>\n"
    text += f"• Trading: {trade_points:,.2f} points\n"
    text += f"• Referrals: {points_data['referrals_points']:,.2f} points\n\n"

    # Referral stats
    text += f"<b>Referral Stats:</b>\n"
    text += f"👥 Active Referrals: {points_data['referrals_count']}\n"

    if points_data['referral_code']:
        text += f"🎫 Your Code: <code>{points_data['referral_code']}</code>\n\n"
    else:
        text += f"\n"

    # How to earn more
    text += f"<b>Earn More Points:</b>\n"
    text += f"• Trade to earn 1 point per $1 volume\n"
    text += f"• Refer friends for 100 bonus points\n"
    text += f"• Earn 10% of your referrals' points\n\n"

    text += f"Use /referral to share your code!"

    keyboard = [[InlineKeyboardButton("🎫 View Referrals", callback_data="referrals")],
                [InlineKeyboardButton("« Main Menu", callback_data="start")]]

    if query:
        await message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    else:
        await message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )


async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's referral code and referral list."""
    query = update.callback_query
    message = query.message if query else update.message
    telegram_id = update.effective_user.id

    # Import referral manager
    from utils.referrals import ReferralManager
    from utils.storage import get_storage

    try:
        storage = get_storage()
        referral_mgr = ReferralManager(storage)

        # Get or create referral code
        referral_code = referral_mgr.get_or_create_referral_code(telegram_id)

        if not referral_code:
            logger.error(f"Failed to get/create referral code for user {telegram_id}")
            error_text = "❌ Failed to get referral code. Please try again later."
            if query:
                await message.edit_text(error_text, parse_mode=ParseMode.HTML)
            else:
                await message.reply_text(error_text, parse_mode=ParseMode.HTML)
            return
    except Exception as e:
        logger.error(f"Error in show_referral for user {telegram_id}: {e}", exc_info=True)
        error_text = f"❌ Failed to get referral code.\n\nError: {str(e)[:100]}"
        if query:
            await message.edit_text(error_text, parse_mode=ParseMode.HTML)
        else:
            await message.reply_text(error_text, parse_mode=ParseMode.HTML)
        return

    # Get user's points and referral data
    points_data = referral_mgr.get_user_points(telegram_id)
    referrals = referral_mgr.get_referrals_list(telegram_id, limit=10)

    # Format text
    text = f"🎫 <b>Your Referral Code</b>\n\n"
    text += f"<code>{referral_code}</code>\n\n"

    text += f"<b>Share this code with friends to earn:</b>\n"
    text += f"• 100 points when they sign up\n"
    text += f"• 10% of their trading points forever\n\n"

    # Referral stats
    text += f"<b>Your Referral Stats:</b>\n"
    text += f"👥 Total Referrals: {points_data['referrals_count']}\n"
    text += f"⭐ Points from Referrals: {points_data['referrals_points']:,.2f}\n\n"

    # List referrals
    if referrals:
        text += f"<b>Recent Referrals:</b>\n"
        for i, ref in enumerate(referrals[:5], 1):
            username = ref['username'][:20] if len(ref['username']) > 20 else ref['username']
            text += f"{i}. @{username} - {ref['total_points']:,.0f} pts (${ref['total_volume']:,.0f})\n"

        if len(referrals) > 5:
            text += f"\n...and {len(referrals) - 5} more\n"
    else:
        text += f"<i>No referrals yet. Share your code to start earning!</i>\n"

    text += f"\n💡 Tip: Customize your code in Settings"

    keyboard = [
        [InlineKeyboardButton("⚙️ Change Code", callback_data="change_referral_code")],
        [InlineKeyboardButton("⭐ View Points", callback_data="show_points")],
        [InlineKeyboardButton("« Main Menu", callback_data="start")],
    ]

    if query:
        await message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    else:
        await message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )


# Conversation states for changing referral code
CHANGE_REFERRAL_CODE = range(1)


async def change_referral_code_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to enter new referral code."""
    query = update.callback_query
    await query.answer()

    text = (
        "⚙️ <b>Change Referral Code</b>\n\n"
        "Enter your new referral code:\n\n"
        "<b>Requirements:</b>\n"
        "• 3-7 characters\n"
        "• Letters and numbers only\n"
        "• Must be unique\n\n"
        "Send /cancel to cancel"
    )

    keyboard = [[InlineKeyboardButton("« Cancel", callback_data="referrals")]]

    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

    return CHANGE_REFERRAL_CODE


async def handle_new_referral_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the new referral code input."""
    new_code = update.message.text.strip().upper()
    telegram_id = update.effective_user.id

    from utils.referrals import ReferralManager
    from utils.storage import get_storage

    try:
        storage = get_storage()
        referral_mgr = ReferralManager(storage)

        # Set the new code
        success, message = referral_mgr.set_referral_code(telegram_id, new_code)

        if success:
            text = f"✅ <b>Referral Code Updated!</b>\n\n"
            text += f"Your new code: <code>{new_code}</code>\n\n"
            text += f"Share it with friends to start earning points!"
        else:
            text = f"❌ <b>Failed to Update Code</b>\n\n"
            text += message

        keyboard = [[InlineKeyboardButton("« Back to Referrals", callback_data="referrals")]]

        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Error changing referral code for user {telegram_id}: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error: {str(e)[:100]}",
            parse_mode=ParseMode.HTML
        )

    return ConversationHandler.END


# ============================================================================
# AUTO-RELOAD BACKGROUND TASK
# ============================================================================


async def auto_reload_task(application) -> None:
    """
    Background task that checks for resolved markets and auto-reloads winnings.

    This task runs every 5 minutes and:
    1. Gets all users with active positions
    2. For each user with auto_reload enabled:
       - Checks all their positions
       - Finds markets that are resolved (status == 4)
       - Redeems winnings automatically
       - Sends notification to user
    """
    while True:
        try:
            # Wait 5 minutes between checks
            await asyncio.sleep(300)

            logger.info("Running auto-reload check...")

            # Get all active users from storage
            from utils.storage import get_storage

            storage = get_storage()
            active_users = storage.get_all_active_users()

            for telegram_id in active_users:
                try:
                    # Get user settings from persistent storage
                    settings = get_persistent_user_settings(telegram_id)
                    if not settings.get("auto_reload", False):
                        continue

                    # Get user's Polymarket client
                    client = get_user_polymarket_client(telegram_id)
                    if not client:
                        continue

                    # Get user's account manager for wallet address
                    account_mgr = get_user_account_manager(telegram_id)
                    if not account_mgr:
                        continue

                    wallet_address = account_mgr.get_address()

                    # Get all positions
                    positions = client.get_positions(address=wallet_address)

                    if not positions:
                        continue

                    # Check each position for resolved markets
                    redeemed_count = 0
                    total_redeemed = 0.0

                    for position in positions:
                        # Get market details
                        market = client.get_market(position.marketId)

                        # Check if market is resolved (status == 4)
                        if market.status == 4:
                            # Check if position has shares to redeem
                            if position.shares > 0:
                                try:
                                    # Redeem winnings
                                    result = client.redeem(position.marketId)

                                    if result:
                                        redeemed_count += 1
                                        # Calculate approximate redeemed amount
                                        # For winning positions, shares convert 1:1 to USDT
                                        redeemed_amount = position.shares
                                        total_redeemed += redeemed_amount

                                        logger.info(
                                            f"Auto-reloaded {redeemed_amount:.2f} USDT "
                                            f"from market {market.title} for user {telegram_id}"
                                        )
                                except Exception as e:
                                    logger.error(
                                        f"Failed to redeem market {position.marketId} "
                                        f"for user {telegram_id}: {e}"
                                    )

                    # Send notification to user if any positions were redeemed
                    if redeemed_count > 0:
                        notification_text = (
                            f"🎉 <b>Auto-Reload Complete!</b>\n\n"
                            f"Reloaded <b>{redeemed_count}</b> position(s)\n"
                            f"Total: <b>${total_redeemed:.2f} USDT</b>\n\n"
                            f"Winnings have been credited to your wallet."
                        )

                        try:
                            await application.bot.send_message(
                                chat_id=telegram_id,
                                text=notification_text,
                                parse_mode=ParseMode.HTML,
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to send notification to user {telegram_id}: {e}"
                            )

                except Exception as e:
                    logger.error(
                        f"Error processing auto-reload for user {telegram_id}: {e}"
                    )

        except Exception as e:
            logger.error(f"Error in auto-reload task: {e}")
            # Continue running even if there's an error


# ============================================================================
# COPYTRADING HANDLERS
# ============================================================================


async def show_copytrading(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show copytrading menu with user's subscriptions."""
    telegram_id = update.effective_user.id
    manager = get_copytrading_manager()

    if not manager:
        text = "❌ Copytrading not initialized."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back", callback_data="start")]
        ])
    else:
        subs = manager.get_user_subscriptions(telegram_id)

        if not subs:
            text = (
                "<b>📋 Copytrading</b>\n\n"
                "You're not copying anyone yet.\n\n"
                "Add a wallet to automatically mirror\n"
                "their trades at your chosen scale."
            )
        else:
            text = "<b>📋 Copytrading</b>\n\n<b>Your Subscriptions:</b>\n\n"
            for sub in subs:
                status = "✅" if sub.enabled else "⏸️"
                text += (
                    f"{status} <b>{sub.target_name}</b>\n"
                    f"   <code>{sub.target_wallet[:16]}...</code>\n"
                    f"   Scale: {sub.scale_factor*100:.0f}%\n\n"
                )

        buttons = [[InlineKeyboardButton("➕ Add Wallet", callback_data="copy_add")]]

        # Add buttons for each subscription
        for sub in (subs if manager else []):
            toggle_text = "⏸️ Pause" if sub.enabled else "▶️ Resume"
            buttons.append([
                InlineKeyboardButton(
                    f"{sub.target_name[:15]}",
                    callback_data=f"copy_toggle:{sub.target_wallet}"
                ),
                InlineKeyboardButton(
                    "🗑️",
                    callback_data=f"copy_delete:{sub.target_wallet}"
                ),
            ])

        buttons.append([InlineKeyboardButton("« Back", callback_data="start")])
        keyboard = InlineKeyboardMarkup(buttons)

    query = update.callback_query
    if query:
        await query.message.edit_text(
            text, reply_markup=keyboard, parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            text, reply_markup=keyboard, parse_mode=ParseMode.HTML
        )


async def initiate_copy_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start adding a copytrading subscription."""
    query = update.callback_query

    text = (
        "<b>➕ Add Copytrading Subscription</b>\n\n"
        "Send the wallet address you want to copy.\n\n"
        "<i>Send /cancel to abort</i>"
    )

    await query.message.edit_text(text, parse_mode=ParseMode.HTML)
    return AWAITING_COPY_WALLET


async def handle_copy_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle wallet address for copytrading."""
    wallet = update.message.text.strip().lower()

    # Basic validation
    if not wallet.startswith("0x") or len(wallet) != 42:
        await update.message.reply_text(
            "❌ Invalid wallet address. Please send a valid Ethereum address."
        )
        return AWAITING_COPY_WALLET

    context.user_data[USER_DATA_COPY_WALLET] = wallet

    await update.message.reply_text(
        "<b>What should we call this wallet?</b>\n\n"
        "Send a friendly name (e.g., 'Top Trader', 'Whale').\n\n"
        "<i>Send /cancel to abort</i>",
        parse_mode=ParseMode.HTML,
    )
    return AWAITING_COPY_NAME


async def handle_copy_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle name for copytrading subscription."""
    name = update.message.text.strip()[:50]  # Limit length
    context.user_data[USER_DATA_COPY_NAME] = name

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("10%", callback_data="copy_scale:0.1"),
            InlineKeyboardButton("25%", callback_data="copy_scale:0.25"),
            InlineKeyboardButton("50%", callback_data="copy_scale:0.5"),
        ],
        [
            InlineKeyboardButton("75%", callback_data="copy_scale:0.75"),
            InlineKeyboardButton("100%", callback_data="copy_scale:1.0"),
        ],
    ])

    await update.message.reply_text(
        f"<b>Copy scale for {name}</b>\n\n"
        "What % of their trade size should you mirror?\n\n"
        "<i>Example: 25% means a $100 trade becomes $25 for you</i>",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    return AWAITING_COPY_SCALE


async def handle_copy_scale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle scale factor selection."""
    query = update.callback_query
    await query.answer()

    scale = float(query.data.split(":")[1])
    wallet = context.user_data.get(USER_DATA_COPY_WALLET)
    name = context.user_data.get(USER_DATA_COPY_NAME)

    telegram_id = update.effective_user.id
    manager = get_copytrading_manager()

    if manager and wallet and name:
        try:
            manager.subscribe(telegram_id, wallet, name, scale)
            text = (
                f"<b>✅ Subscription Added!</b>\n\n"
                f"Now copying <b>{name}</b>\n"
                f"<code>{wallet[:20]}...</code>\n\n"
                f"Scale: {scale*100:.0f}%"
            )
        except Exception as e:
            text = f"❌ Failed to add subscription: {e}"
    else:
        text = "❌ Missing data. Please try again."

    # Clear user data
    context.user_data.pop(USER_DATA_COPY_WALLET, None)
    context.user_data.pop(USER_DATA_COPY_NAME, None)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("« Back to Copytrading", callback_data="copytrading")]
    ])
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    return ConversationHandler.END


async def toggle_copy_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle a copytrading subscription on/off."""
    query = update.callback_query
    await query.answer()

    wallet = query.data.split(":")[1]
    telegram_id = update.effective_user.id
    manager = get_copytrading_manager()

    if manager:
        subs = manager.get_user_subscriptions(telegram_id)
        for sub in subs:
            if sub.target_wallet == wallet:
                new_state = not sub.enabled
                manager.set_subscription_enabled(telegram_id, wallet, new_state)
                status = "enabled" if new_state else "paused"
                await query.answer(f"Subscription {status}")
                break

    # Refresh the menu
    await show_copytrading(update, context)


async def delete_copy_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a copytrading subscription."""
    query = update.callback_query
    await query.answer()

    wallet = query.data.split(":")[1]
    telegram_id = update.effective_user.id
    manager = get_copytrading_manager()

    if manager:
        if manager.unsubscribe(telegram_id, wallet):
            await query.answer("Subscription deleted")
        else:
            await query.answer("Subscription not found")

    # Refresh the menu
    await show_copytrading(update, context)


# ============================================================================
# MAIN
# ============================================================================


def main() -> None:
    """Start the bot."""
    # Get bot token
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")

    # Create application
    application = Application.builder().token(token).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", show_help))
    application.add_handler(CommandHandler("debug", debug))
    application.add_handler(CommandHandler("points", show_points))
    application.add_handler(CommandHandler("referral", show_referral))

    # Command handlers that redirect to button callbacks
    async def markets_command(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /markets command."""

        # Create fake callback query to reuse show_markets function
        class FakeQuery:
            async def answer(self):
                pass

            message = update.message
            data = "markets"

        class FakeUpdate:
            callback_query = FakeQuery()
            effective_user = update.effective_user
            message = update.message

        fake_update = FakeUpdate()
        await show_markets(fake_update, context)

    async def home_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /home command - same as /start."""
        await start(update, context)

    async def positions_command(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /positions command."""

        # Create fake callback query to reuse show_positions function
        class FakeQuery:
            async def answer(self):
                pass

            message = update.message
            data = "positions"

        class FakeUpdate:
            callback_query = FakeQuery()
            effective_user = update.effective_user
            message = update.message

        fake_update = FakeUpdate()
        await show_positions(fake_update, context)

    async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /setup command - shows wallet creation."""
        # Create fake callback query to reuse show_wallet function
        class FakeQuery:
            async def answer(self):
                pass

            message = update.message
            data = "wallet"

        class FakeUpdate:
            callback_query = FakeQuery()
            effective_user = update.effective_user
            message = update.message

        fake_update = FakeUpdate()
        await show_wallet(fake_update, context)

    async def pnl_history_command(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /pnl_history command."""
        # Create fake callback query to reuse show_pnl_history function
        class FakeQuery:
            async def answer(self):
                pass

            message = update.message
            data = "pnl_history"

        class FakeUpdate:
            callback_query = FakeQuery()
            effective_user = update.effective_user
            message = update.message

        fake_update = FakeUpdate()
        await show_pnl_history(fake_update, context)

    application.add_handler(CommandHandler("markets", markets_command))
    application.add_handler(CommandHandler("home", home_command))
    application.add_handler(CommandHandler("positions", positions_command))
    application.add_handler(CommandHandler("setup", setup_command))
    application.add_handler(CommandHandler("pnl_history", pnl_history_command))

    # Search command handler
    async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle /search command with optional keyword argument."""
        # Check if keyword was provided as argument
        keyword = ' '.join(context.args) if context.args else None

        if keyword:
            # Direct search with provided keyword
            # Create a fake message object with the keyword as text
            class FakeMessage:
                def __init__(self, text_content):
                    self.text = text_content

                async def reply_text(self, *args, **kwargs):
                    return await update.message.reply_text(*args, **kwargs)

            fake_message_obj = FakeMessage(keyword)

            # Create fake update with the keyword
            class FakeUpdate:
                def __init__(self):
                    self.message = fake_message_obj
                    self.effective_user = update.effective_user
                    self.callback_query = None

            fake_update = FakeUpdate()

            # Call the search handler directly
            return await handle_search_query(fake_update, context)
        else:
            # No keyword provided, show search prompt
            text = (
                "🔍 <b>Search Markets</b>\n\n"
                "Enter a keyword to search for markets.\n\n"
                "<i>Examples: bitcoin, trump, election, AI, sports</i>\n\n"
                "Type your search term below:"
            )

            keyboard = [[InlineKeyboardButton("« Cancel", callback_data="start")]]

            await update.message.reply_text(
                text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
            )

            return AWAITING_MARKET_SEARCH

    # Add conversation handler for multi-step flows
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_callback),
            CommandHandler("search", search_command),
        ],
        states={
            AWAITING_BET_AMOUNT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    lambda u, c: (
                        handle_custom_limit_amount(u, c)
                        if c.user_data.get("awaiting_limit_custom_amount")
                        else handle_custom_bet_amount(u, c)
                    ),
                )
            ],
            AWAITING_LIMIT_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_limit_price)
            ],
            AWAITING_WALLET_IMPORT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wallet_import)
            ],
            AWAITING_MARKET_SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_query)
            ],
            AWAITING_WITHDRAWAL_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_withdrawal_address)
            ],
            AWAITING_WITHDRAWAL_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_withdrawal_amount)
            ],
            CHANGE_REFERRAL_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_referral_code)
            ],
            AWAITING_COPY_WALLET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_copy_wallet)
            ],
            AWAITING_COPY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_copy_name)
            ],
            AWAITING_COPY_SCALE: [
                CallbackQueryHandler(handle_copy_scale, pattern="^copy_scale:")
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CallbackQueryHandler(button_callback),
        ],
    )
    application.add_handler(conv_handler)

    # Add callback query handler for all other buttons
    application.add_handler(CallbackQueryHandler(button_callback))

    # Initialize copytrading manager
    from utils.copytrading import init_copytrading_manager, get_copytrading_manager
    from utils.user_manager import get_user_polymarket_client

    async def on_mirror_complete(result):
        """Callback when a trade is mirrored - send notification to user."""
        from utils.copytrading import MirrorResult
        if not isinstance(result, MirrorResult):
            return

        user_id = result.subscription.user_id
        trade = result.trade
        sub = result.subscription

        if result.success and result.executed_amount > 0:
            text = (
                f"📋 <b>Copytraded!</b>\n\n"
                f"Copied <b>{sub.target_name}</b>'s trade:\n"
                f"{'🟢 BUY' if trade.is_buy else '🔴 SELL'} ${result.executed_amount:.2f}\n"
                f"Market: {trade.market_slug or trade.token_id[:20]}\n"
            )
        elif result.error:
            text = (
                f"⚠️ <b>Copytrade Failed</b>\n\n"
                f"Failed to copy {sub.target_name}'s trade:\n"
                f"Error: {result.error}\n"
            )
        else:
            return  # Skip notification for skipped trades

        try:
            await application.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.error(f"Failed to send copytrade notification to {user_id}: {e}")

    copytrading_manager = init_copytrading_manager(
        get_user_client=get_user_polymarket_client,
        on_mirror_complete=on_mirror_complete,
        storage_path="copytrading_subs.json",
    )
    logger.info("Copytrading manager initialized")

    # Start background tasks (if job_queue is available)
    if application.job_queue:
        # Auto-reload task (runs every 5 minutes)
        application.job_queue.run_once(
            lambda context: asyncio.create_task(auto_reload_task(context.application)),
            when=15,  # Start 15 seconds after bot starts
        )

        # Copytrading polling task
        async def start_copytrading_polling(context):
            """Start copytrading polling loop."""
            manager = get_copytrading_manager()
            if manager:
                await manager.start_polling(interval_sec=5.0)
                logger.info("Copytrading polling started")

        application.job_queue.run_once(
            lambda context: asyncio.create_task(start_copytrading_polling(context)),
            when=20,  # Start 20 seconds after bot starts
        )

        logger.info("Background tasks scheduled")
    else:
        logger.warning("JobQueue not available - background tasks disabled")

    # Register commands with Telegram for autocomplete
    from telegram import BotCommand

    async def register_commands(application: Application) -> None:
        """Register bot commands after initialization."""
        commands = [
            BotCommand("home", "Launch the bot and display the main menu"),
            BotCommand("help", "Show information and available commands"),
            BotCommand("setup", "Guide for setting up your Safe wallet for Polymarket trading"),
            BotCommand("markets", "Browse all active prediction markets"),
            BotCommand("search", "Search for markets by keyword"),
            BotCommand("positions", "View your open positions"),
            BotCommand("pnl_history", "View your PnL over time"),
            BotCommand("points", "View your Polymarket points"),
            BotCommand("referral", "Get your unique code and view your referrals"),
        ]

        await application.bot.set_my_commands(commands)
        logger.info(f"Registered {len(commands)} bot commands with Telegram")

    # Set post_init callback
    application.post_init = register_commands

    # Start bot
    logger.info("Starting Polymarket Trading Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
