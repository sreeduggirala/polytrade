"""
Comprehensive unit tests for bot.py

Tests all functions, handlers, and bot logic using pytest with mocking.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, AsyncMock, patch, call
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, User, Message, CallbackQuery, Chat
from telegram.ext import ContextTypes

import bot
from bot import (
    get_user_settings,
    format_price,
    format_pnl,
    get_pnl_emoji,
    get_main_menu_keyboard,
    start,
    show_markets,
    show_market_details,
    initiate_buy,
    handle_bet_amount,
    show_trade_confirmation,
    execute_trade,
    show_positions,
    show_position_details,
    show_settings,
    toggle_setting,
    generate_position_card,
    button_callback,
    show_help,
    USER_DATA_MARKET,
    USER_DATA_SIDE,
    USER_DATA_WALLET,
    USER_DATA_SETTINGS,
    AWAITING_BET_AMOUNT,
    AWAITING_MARKET_SEARCH,
    AWAITING_LIMIT_PRICE,
    AWAITING_WALLET_IMPORT,
)


# ============================================================================
# Test Utility Functions
# ============================================================================

class TestGetUserSettings:
    """Test get_user_settings function."""

    def test_get_user_settings_initializes_defaults(self):
        """Test that user settings are initialized with defaults."""
        context = MagicMock()
        context.user_data = {}

        settings = get_user_settings(context)

        assert settings["auto_reload"] is True
        assert settings["confirm_trades"] is True
        assert settings["show_pnl"] is True
        assert settings["show_charts"] is True
        assert settings["language"] == "en"

    def test_get_user_settings_returns_existing_settings(self):
        """Test that existing settings are returned."""
        context = MagicMock()
        existing_settings = {
            "auto_reload": False,
            "confirm_trades": False,
            "show_pnl": False,
            "show_charts": False,
            "language": "es",
        }
        context.user_data = {USER_DATA_SETTINGS: existing_settings}

        settings = get_user_settings(context)

        assert settings == existing_settings
        assert settings["auto_reload"] is False
        assert settings["language"] == "es"


class TestFormatPrice:
    """Test format_price function."""

    def test_format_price_basic(self):
        """Test basic price formatting."""
        assert format_price(0.5) == "$0.500"
        assert format_price(0.123) == "$0.123"
        assert format_price(1.0) == "$1.000"

    def test_format_price_with_decimals(self):
        """Test price formatting with various decimal values."""
        assert format_price(0.12345) == "$0.123"
        assert format_price(0.999) == "$0.999"
        assert format_price(0.001) == "$0.001"

    def test_format_price_whole_numbers(self):
        """Test price formatting with whole numbers."""
        assert format_price(1) == "$1.000"
        assert format_price(10) == "$10.000"
        assert format_price(100) == "$100.000"


class TestFormatPnL:
    """Test format_pnl function."""

    def test_format_pnl_positive(self):
        """Test positive PnL formatting."""
        assert format_pnl(100.0) == "+$100.00"
        assert format_pnl(50.5) == "+$50.50"
        assert format_pnl(0.01) == "+$0.01"

    def test_format_pnl_negative(self):
        """Test negative PnL formatting."""
        assert format_pnl(-100.0) == "-$100.00"
        assert format_pnl(-50.5) == "-$50.50"
        assert format_pnl(-0.01) == "-$0.01"

    def test_format_pnl_zero(self):
        """Test zero PnL formatting."""
        assert format_pnl(0.0) == "+$0.00"
        assert format_pnl(0) == "+$0.00"


class TestGetPnLEmoji:
    """Test get_pnl_emoji function."""

    def test_get_pnl_emoji_positive(self):
        """Test emoji for positive PnL."""
        assert get_pnl_emoji(100.0) == "📈"
        assert get_pnl_emoji(0.01) == "📈"
        assert get_pnl_emoji(1000) == "📈"

    def test_get_pnl_emoji_negative(self):
        """Test emoji for negative PnL."""
        assert get_pnl_emoji(-100.0) == "📉"
        assert get_pnl_emoji(-0.01) == "📉"
        assert get_pnl_emoji(-1000) == "📉"

    def test_get_pnl_emoji_zero(self):
        """Test emoji for zero PnL."""
        assert get_pnl_emoji(0.0) == "➖"
        assert get_pnl_emoji(0) == "➖"


# ============================================================================
# Test Main Menu
# ============================================================================

class TestGetMainMenuKeyboard:
    """Test get_main_menu_keyboard function."""

    def test_get_main_menu_keyboard_structure(self):
        """Test that main menu keyboard has correct structure."""
        keyboard = get_main_menu_keyboard()

        assert isinstance(keyboard, InlineKeyboardMarkup)
        assert len(keyboard.inline_keyboard) == 4  # 4 rows
        assert len(keyboard.inline_keyboard[0]) == 2  # Markets, Positions
        assert len(keyboard.inline_keyboard[1]) == 2  # Trading Card, PnL History
        assert len(keyboard.inline_keyboard[2]) == 2  # Settings, Wallet
        assert len(keyboard.inline_keyboard[3]) == 2  # Help, Refresh

    def test_get_main_menu_keyboard_buttons(self):
        """Test that main menu has correct button labels and callbacks."""
        keyboard = get_main_menu_keyboard()

        # Row 1
        assert keyboard.inline_keyboard[0][0].text == "📊 Markets"
        assert keyboard.inline_keyboard[0][0].callback_data == "markets"
        assert keyboard.inline_keyboard[0][1].text == "🔍 Search"
        assert keyboard.inline_keyboard[0][1].callback_data == "search_markets"

        # Row 2
        assert keyboard.inline_keyboard[1][0].text == "💼 Positions"
        assert keyboard.inline_keyboard[1][0].callback_data == "positions"
        assert keyboard.inline_keyboard[1][1].text == "🎴 Trading Card"
        assert keyboard.inline_keyboard[1][1].callback_data == "generate_card"

        # Row 3
        assert keyboard.inline_keyboard[2][0].text == "📈 PnL History"
        assert keyboard.inline_keyboard[2][0].callback_data == "pnl_history"
        assert keyboard.inline_keyboard[2][1].text == "💰 Wallet"
        assert keyboard.inline_keyboard[2][1].callback_data == "wallet"

        # Row 4
        assert keyboard.inline_keyboard[3][0].text == "⚙️ Settings"
        assert keyboard.inline_keyboard[3][0].callback_data == "settings"
        assert keyboard.inline_keyboard[3][1].text == "❓ Help"
        assert keyboard.inline_keyboard[3][1].callback_data == "help"


@pytest.mark.asyncio
class TestStart:
    """Test start command handler."""

    @pytest.mark.anyio
    async def test_start_with_message(self):
        """Test start command with a message update."""
        # Mock update and context
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(spec=User)
        update.effective_user.first_name = "Alice"
        update.message = AsyncMock(spec=Message)
        update.callback_query = None

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Call start
        await start(update, context)

        # Verify message was sent
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "Welcome to Polymarket Trading Bot, Alice!" in call_args[0][0]
        assert call_args[1]["reply_markup"] is not None

    @pytest.mark.anyio
    async def test_start_with_callback_query(self):
        """Test start command with a callback query update."""
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(spec=User)
        update.effective_user.first_name = "Bob"
        update.message = None
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.message = AsyncMock(spec=Message)

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        await start(update, context)

        # Verify message was edited
        update.callback_query.message.edit_text.assert_called_once()
        call_args = update.callback_query.message.edit_text.call_args
        assert "Welcome to Polymarket Trading Bot, Bob!" in call_args[0][0]


# ============================================================================
# Test Markets Browser
# ============================================================================

@pytest.mark.asyncio
class TestShowMarkets:
    """Test show_markets handler."""

    @pytest.mark.anyio
    async def test_show_markets_success(self):
        """Test showing markets with available markets."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.message = AsyncMock(spec=Message)

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Mock PolymarketClient
        mock_market = MagicMock()
        mock_market.marketTitle = "BTC > $100k by EOY"
        mock_market.topicId = "market_123"
        mock_market.volume = 10000.0

        with patch('bot.PolymarketClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_markets.return_value = [mock_market]
            mock_client_class.return_value = mock_client

            await show_markets(update, context)

        update.callback_query.answer.assert_called_once()
        update.callback_query.message.edit_text.assert_called_once()

        call_args = update.callback_query.message.edit_text.call_args
        assert "Active Markets" in call_args[0][0]

    @pytest.mark.anyio
    async def test_show_markets_no_markets(self):
        """Test showing markets when no markets are available."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.message = AsyncMock(spec=Message)

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with patch('bot.PolymarketClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_markets.return_value = []
            mock_client_class.return_value = mock_client

            await show_markets(update, context)

        call_args = update.callback_query.message.edit_text.call_args
        assert "No active markets found" in call_args[0][0]

    @pytest.mark.anyio
    async def test_show_markets_exception_handling(self):
        """Test error handling when PolymarketClient fails."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.message = AsyncMock(spec=Message)

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with patch('bot.PolymarketClient') as mock_client_class:
            mock_client_class.side_effect = Exception("API Error")

            await show_markets(update, context)

        # Should handle exception gracefully
        update.callback_query.answer.assert_called_once()


# ============================================================================
# Test Trading Flow
# ============================================================================

@pytest.mark.asyncio
class TestInitiateBuy:
    """Test initiate_buy handler."""

    @pytest.mark.anyio
    async def test_initiate_buy_shows_bet_amounts(self):
        """Test that initiate_buy shows bet amount options."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.message = AsyncMock(spec=Message)
        update.callback_query.data = "buy_yes_market_123"

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}

        result = await initiate_buy(update, context)

        assert result == AWAITING_BET_AMOUNT
        update.callback_query.answer.assert_called_once()
        update.callback_query.message.edit_text.assert_called_once()

        call_args = update.callback_query.message.edit_text.call_args
        assert "Select bet amount" in call_args[0][0]

    @pytest.mark.anyio
    async def test_initiate_buy_stores_market_data(self):
        """Test that initiate_buy stores market and side in user_data."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.message = AsyncMock(spec=Message)
        update.callback_query.data = "buy_no_market_456"

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}

        await initiate_buy(update, context)

        assert context.user_data[USER_DATA_MARKET] == "market_456"
        assert context.user_data[USER_DATA_SIDE] == "NO"


@pytest.mark.asyncio
class TestHandleBetAmount:
    """Test handle_bet_amount handler."""

    @pytest.mark.anyio
    async def test_handle_bet_amount_preset(self):
        """Test handling preset bet amount."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.message = AsyncMock(spec=Message)
        update.callback_query.data = "bet_50"

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            USER_DATA_MARKET: "market_123",
            USER_DATA_SIDE: "YES"
        }

        with patch('bot.show_trade_confirmation', new_callable=AsyncMock) as mock_confirm:
            result = await handle_bet_amount(update, context)

        mock_confirm.assert_called_once()
        assert "bet_amount" in context.user_data

    @pytest.mark.anyio
    async def test_handle_bet_amount_default(self):
        """Test handling default bet amount from settings."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.message = AsyncMock(spec=Message)
        update.callback_query.data = "bet_default"

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            USER_DATA_MARKET: "market_123",
            USER_DATA_SIDE: "YES",
            USER_DATA_SETTINGS: {"default_bet": 25.0}
        }

        with patch('bot.show_trade_confirmation', new_callable=AsyncMock):
            await handle_bet_amount(update, context)

        assert context.user_data["bet_amount"] == 25.0


# ============================================================================
# Test Position Management
# ============================================================================

@pytest.mark.asyncio
class TestShowPositions:
    """Test show_positions handler."""

    @pytest.mark.anyio
    async def test_show_positions_with_positions(self):
        """Test showing positions when user has positions."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.message = AsyncMock(spec=Message)

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {USER_DATA_WALLET: "0x123"}

        mock_position = MagicMock()
        mock_position.marketTitle = "Test Market"
        mock_position.tokenName = "YES"
        mock_position.shares = 1000.0
        mock_position.unrealizedPnl = 50.0
        mock_position.realizedPnl = 10.0
        mock_position.topicId = "topic_123"
        mock_position.currentValue = 1060.0

        with patch('bot.PolymarketClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_positions.return_value = [mock_position]
            mock_client_class.return_value = mock_client

            await show_positions(update, context)

        call_args = update.callback_query.message.edit_text.call_args
        assert "Your Positions" in call_args[0][0]

    @pytest.mark.anyio
    async def test_show_positions_no_positions(self):
        """Test showing positions when user has no positions."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.message = AsyncMock(spec=Message)

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {USER_DATA_WALLET: "0x123"}

        with patch('bot.PolymarketClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_positions.return_value = []
            mock_client_class.return_value = mock_client

            await show_positions(update, context)

        call_args = update.callback_query.message.edit_text.call_args
        assert "no open positions" in call_args[0][0]

    @pytest.mark.anyio
    async def test_show_positions_no_wallet(self):
        """Test showing positions when user has no wallet configured."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.message = AsyncMock(spec=Message)

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}

        await show_positions(update, context)

        call_args = update.callback_query.message.edit_text.call_args
        assert "No wallet connected" in call_args[0][0]


# ============================================================================
# Test Settings
# ============================================================================

@pytest.mark.asyncio
class TestShowSettings:
    """Test show_settings handler."""

    @pytest.mark.anyio
    async def test_show_settings_displays_all_settings(self):
        """Test that show_settings displays all settings correctly."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.message = AsyncMock(spec=Message)

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            USER_DATA_SETTINGS: {
                "auto_reload": True,
                "confirm_trades": True,
                "show_pnl": False,
                "show_charts": True,
            }
        }

        await show_settings(update, context)

        call_args = update.callback_query.message.edit_text.call_args
        text = call_args[0][0]

        assert "Settings" in text
        assert "Auto-Reload" in text or "AutoReload" in text
        assert "🟢 ON" in text  # Auto-Reload is ON
        assert "🔴" in text or "Hide" in text  # PnL is hidden


@pytest.mark.asyncio
class TestToggleSetting:
    """Test toggle_setting handler."""

    @pytest.mark.anyio
    async def test_toggle_setting_auto_reload(self):
        """Test toggling auto_reload setting."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.message = AsyncMock(spec=Message)
        update.callback_query.data = "toggle_auto_reload"

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            USER_DATA_SETTINGS: {"auto_reload": False}
        }

        with patch('bot.show_settings', new_callable=AsyncMock):
            await toggle_setting(update, context)

        assert context.user_data[USER_DATA_SETTINGS]["auto_reload"] is True

    @pytest.mark.anyio
    async def test_toggle_setting_confirm_trades(self):
        """Test toggling confirm_trades setting."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.message = AsyncMock(spec=Message)
        update.callback_query.data = "toggle_confirm"

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {
            USER_DATA_SETTINGS: {"confirm_trades": True}
        }

        with patch('bot.show_settings', new_callable=AsyncMock):
            await toggle_setting(update, context)

        assert context.user_data[USER_DATA_SETTINGS]["confirm_trades"] is False


# ============================================================================
# Test Help
# ============================================================================

@pytest.mark.asyncio
class TestShowHelp:
    """Test show_help handler."""

    @pytest.mark.anyio
    async def test_show_help_with_callback_query(self):
        """Test show_help with callback query."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.message = AsyncMock(spec=Message)
        update.message = None

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        await show_help(update, context)

        update.callback_query.answer.assert_called_once()
        update.callback_query.message.edit_text.assert_called_once()

        call_args = update.callback_query.message.edit_text.call_args
        assert "Help - Polymarket Trading Bot" in call_args[0][0]
        assert "/start" in call_args[0][0]
        assert "/markets" in call_args[0][0]

    @pytest.mark.anyio
    async def test_show_help_with_message(self):
        """Test show_help with message (command)."""
        update = MagicMock(spec=Update)
        update.message = AsyncMock(spec=Message)
        update.callback_query = None

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        await show_help(update, context)

        update.message.reply_text.assert_called_once()

        call_args = update.message.reply_text.call_args
        assert "Help - Polymarket Trading Bot" in call_args[0][0]


# ============================================================================
# Test Button Callback Router
# ============================================================================

@pytest.mark.asyncio
class TestButtonCallback:
    """Test button_callback router."""

    @pytest.mark.anyio
    async def test_button_callback_start(self):
        """Test routing to start."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.data = "start"

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with patch('bot.start', new_callable=AsyncMock) as mock_start:
            await button_callback(update, context)
            mock_start.assert_called_once_with(update, context)

    @pytest.mark.anyio
    async def test_button_callback_markets(self):
        """Test routing to markets."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.data = "markets"

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with patch('bot.show_markets', new_callable=AsyncMock) as mock_markets:
            await button_callback(update, context)
            mock_markets.assert_called_once_with(update, context)

    @pytest.mark.anyio
    async def test_button_callback_positions(self):
        """Test routing to positions."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.data = "positions"

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with patch('bot.show_positions', new_callable=AsyncMock) as mock_positions:
            await button_callback(update, context)
            mock_positions.assert_called_once_with(update, context)

    @pytest.mark.anyio
    async def test_button_callback_settings(self):
        """Test routing to settings."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.data = "settings"

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with patch('bot.show_settings', new_callable=AsyncMock) as mock_settings:
            await button_callback(update, context)
            mock_settings.assert_called_once_with(update, context)

    @pytest.mark.anyio
    async def test_button_callback_unknown(self):
        """Test routing with unknown callback data."""
        update = MagicMock(spec=Update)
        update.callback_query = AsyncMock(spec=CallbackQuery)
        update.callback_query.data = "unknown_action"

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        await button_callback(update, context)

        # Should answer the query but not crash
        update.callback_query.answer.assert_called()


# ============================================================================
# Test Constants
# ============================================================================

class TestConstants:
    """Test conversation state constants."""

    def test_conversation_states(self):
        """Test that conversation state constants are defined."""
        assert AWAITING_BET_AMOUNT == 0
        assert AWAITING_MARKET_SEARCH == 1
        assert AWAITING_LIMIT_PRICE == 2
        assert AWAITING_WALLET_IMPORT == 3

    def test_user_data_keys(self):
        """Test that user data key constants are defined."""
        assert USER_DATA_MARKET == "current_market"
        assert USER_DATA_SIDE == "current_side"
        assert USER_DATA_WALLET == "wallet_address"
        assert USER_DATA_SETTINGS == "settings"


# ============================================================================
# Test Main Function
# ============================================================================

class TestMain:
    """Test main function."""

    def test_main_requires_bot_token(self):
        """Test that main raises error without bot token."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN not found"):
                bot.main()

    def test_main_creates_application(self):
        """Test that main creates application with token."""
        mock_token = "test_token_123"

        with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': mock_token}):
            with patch('bot.Application.builder') as mock_builder:
                mock_app_builder = MagicMock()
                mock_app = MagicMock()
                mock_app.run_polling = MagicMock()

                mock_builder.return_value = mock_app_builder
                mock_app_builder.token.return_value = mock_app_builder
                mock_app_builder.build.return_value = mock_app

                bot.main()

                mock_builder.assert_called_once()
                mock_app_builder.token.assert_called_once_with(mock_token)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
