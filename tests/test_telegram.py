"""
Comprehensive unit tests for telegram.py

Tests all functions in the Telegram integration module using pytest.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, AsyncMock, call
import asyncio
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.telegram import (
    download_user_profile_pic,
    get_display_name,
    generate_card_for_user,
    generate_card_for_position,
)


# ============================================================================
# Test download_user_profile_pic
# ============================================================================

class TestDownloadUserProfilePic:
    """Test download_user_profile_pic function."""

    @pytest.mark.asyncio
    @pytest.mark.anyio
    async def test_download_success(self):
        """Test successful profile picture download."""
        # Mock bot
        mock_bot = AsyncMock()

        # Mock photo structure
        mock_photo = MagicMock()
        mock_photo.file_id = "file123"

        # Mock photos response
        mock_photos = MagicMock()
        mock_photos.total_count = 1
        mock_photos.photos = [[mock_photo]]  # List of photo lists
        mock_bot.get_user_profile_photos.return_value = mock_photos

        # Mock file
        mock_file = AsyncMock()
        mock_file.download_to_drive = AsyncMock()
        mock_bot.get_file.return_value = mock_file

        user_id = 12345

        with patch('pathlib.Path.mkdir'):
            result = await download_user_profile_pic(mock_bot, user_id)

        # Verify bot methods called
        mock_bot.get_user_profile_photos.assert_called_once_with(user_id, limit=1)
        mock_bot.get_file.assert_called_once_with("file123")

        # Verify result is a Path
        assert isinstance(result, Path)
        assert str(result).endswith("12345.jpg")

    @pytest.mark.asyncio
    @pytest.mark.anyio
    async def test_download_no_photos(self):
        """Test download when user has no profile photos."""
        mock_bot = AsyncMock()

        # Mock empty photos response
        mock_photos = MagicMock()
        mock_photos.total_count = 0
        mock_photos.photos = []
        mock_bot.get_user_profile_photos.return_value = mock_photos

        user_id = 12345

        with patch('pathlib.Path.mkdir'):
            result = await download_user_profile_pic(mock_bot, user_id)

        # Should return None when no photos
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.anyio
    async def test_download_exception(self):
        """Test download handles exceptions gracefully."""
        mock_bot = AsyncMock()
        mock_bot.get_user_profile_photos.side_effect = Exception("Network error")

        user_id = 12345

        with patch('pathlib.Path.mkdir'):
            with patch('builtins.print'):  # Suppress error print
                result = await download_user_profile_pic(mock_bot, user_id)

        # Should return None on error
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.anyio
    async def test_download_creates_directory(self):
        """Test that profile_pics directory is created."""
        mock_bot = AsyncMock()

        mock_photo = MagicMock()
        mock_photo.file_id = "file456"

        mock_photos = MagicMock()
        mock_photos.total_count = 1
        mock_photos.photos = [[mock_photo]]
        mock_bot.get_user_profile_photos.return_value = mock_photos

        mock_file = AsyncMock()
        mock_bot.get_file.return_value = mock_file

        user_id = 67890

        with patch('pathlib.Path.mkdir') as mock_mkdir:
            await download_user_profile_pic(mock_bot, user_id)

        # Verify directory creation called
        mock_mkdir.assert_called_once_with(exist_ok=True)


# ============================================================================
# Test get_display_name
# ============================================================================

class TestGetDisplayName:
    """Test get_display_name function."""

    def test_get_display_name_with_username(self):
        """Test getting display name when user has username."""
        mock_user = MagicMock()
        mock_user.username = "alice123"
        mock_user.first_name = "Alice"

        name = get_display_name(mock_user)

        assert name == "alice123"

    def test_get_display_name_without_username(self):
        """Test getting display name when user has no username."""
        mock_user = MagicMock()
        mock_user.username = None
        mock_user.first_name = "Bob"

        name = get_display_name(mock_user)

        assert name == "Bob"

    def test_get_display_name_empty_username(self):
        """Test getting display name with empty username."""
        mock_user = MagicMock()
        mock_user.username = ""
        mock_user.first_name = "Charlie"

        name = get_display_name(mock_user)

        # Empty string is falsy, so should use first_name
        assert name == "Charlie"


# ============================================================================
# Test generate_card_for_user
# ============================================================================

class TestGenerateCardForUser:
    """Test generate_card_for_user function."""

    @pytest.mark.asyncio
    @patch('utils.telegram.download_user_profile_pic')
    @patch('utils.telegram.TradingCard')
    @pytest.mark.anyio
    async def test_generate_card_with_profile_pic(self, mock_card_class, mock_download):
        """Test generating card with user profile picture."""
        # Mock bot and user
        mock_bot = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = 12345
        mock_user.username = "testuser"

        # Mock download returning profile pic path
        mock_download.return_value = Path("/tmp/profile_pics/12345.jpg")

        # Mock TradingCard
        mock_card = MagicMock()
        mock_card.save = MagicMock()
        mock_card_class.return_value = mock_card

        with patch('pathlib.Path.mkdir'):
            result = await generate_card_for_user(
                bot=mock_bot,
                user=mock_user,
                market="BTC > $100k",
                position_type="YES",
                pnl_amount=1000.0,
                avg_price=0.65,
                current_price=0.75,
                shares=5000.0
            )

        # Verify download was called
        mock_download.assert_called_once_with(mock_bot, 12345)

        # Verify TradingCard was created with correct params
        mock_card_class.assert_called_once()
        call_kwargs = mock_card_class.call_args[1]
        assert call_kwargs["username"] == "testuser"
        assert call_kwargs["market"] == "BTC > $100k"
        assert call_kwargs["position_type"] == "YES"
        assert call_kwargs["pnl_amount"] == 1000.0
        assert call_kwargs["user_icon_path"] == "/tmp/profile_pics/12345.jpg"

        # Verify card was saved
        mock_card.save.assert_called_once()

        # Verify result is a Path
        assert isinstance(result, Path)

    @pytest.mark.asyncio
    @patch('utils.telegram.download_user_profile_pic')
    @patch('utils.telegram.TradingCard')
    @pytest.mark.anyio
    async def test_generate_card_without_profile_pic(self, mock_card_class, mock_download):
        """Test generating card without user profile picture."""
        mock_bot = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = 67890
        mock_user.username = None
        mock_user.first_name = "Alice"

        # Mock download returning None (no profile pic)
        mock_download.return_value = None

        mock_card = MagicMock()
        mock_card_class.return_value = mock_card

        with patch('pathlib.Path.mkdir'):
            result = await generate_card_for_user(
                bot=mock_bot,
                user=mock_user,
                market="ETH > $5k",
                position_type="NO",
                pnl_amount=-500.0,
                avg_price=0.45,
                current_price=0.35,
                shares=2000.0
            )

        # Verify TradingCard created with None icon path
        call_kwargs = mock_card_class.call_args[1]
        assert call_kwargs["username"] == "Alice"  # Uses first_name
        assert call_kwargs["user_icon_path"] is None

    @pytest.mark.asyncio
    @patch('utils.telegram.download_user_profile_pic')
    @patch('utils.telegram.TradingCard')
    @pytest.mark.anyio
    async def test_generate_card_creates_output_directory(self, mock_card_class, mock_download):
        """Test that output directory is created."""
        mock_bot = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = 11111
        mock_user.username = "bob"

        mock_download.return_value = None
        mock_card = MagicMock()
        mock_card_class.return_value = mock_card

        with patch('pathlib.Path.mkdir') as mock_mkdir:
            await generate_card_for_user(
                bot=mock_bot,
                user=mock_user,
                market="Test",
                position_type="YES",
                pnl_amount=100.0,
                avg_price=0.5,
                current_price=0.6,
                shares=1000.0
            )

        # Verify mkdir was called for output directory
        mock_mkdir.assert_called()

    @pytest.mark.asyncio
    @patch('utils.telegram.download_user_profile_pic')
    @patch('utils.telegram.TradingCard')
    @pytest.mark.anyio
    async def test_generate_card_with_all_parameters(self, mock_card_class, mock_download):
        """Test all card parameters are passed correctly."""
        mock_bot = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = 99999
        mock_user.username = "trader"

        mock_download.return_value = Path("/tmp/99999.jpg")
        mock_card = MagicMock()
        mock_card_class.return_value = mock_card

        market = "SOL flips ETH by market cap"
        position = "YES"
        pnl = 2500.75
        avg = 0.42
        current = 0.87
        shares_count = 12500.0

        with patch('pathlib.Path.mkdir'):
            await generate_card_for_user(
                bot=mock_bot,
                user=mock_user,
                market=market,
                position_type=position,
                pnl_amount=pnl,
                avg_price=avg,
                current_price=current,
                shares=shares_count
            )

        call_kwargs = mock_card_class.call_args[1]
        assert call_kwargs["market"] == market
        assert call_kwargs["position_type"] == position
        assert call_kwargs["pnl_amount"] == pnl
        assert call_kwargs["avg_price"] == avg
        assert call_kwargs["current_price"] == current
        assert call_kwargs["shares"] == shares_count


# ============================================================================
# Test generate_card_for_position
# ============================================================================

class TestGenerateCardForPosition:
    """Test generate_card_for_position function."""

    @pytest.mark.asyncio
    @patch('utils.telegram.generate_card_for_user')
    @pytest.mark.anyio
    async def test_generate_card_for_position(self, mock_generate_card):
        """Test generating card from Position object."""
        # Mock bot and user
        mock_bot = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = 12345

        # Create mock Position object
        mock_position = MagicMock()
        mock_position.marketTitle = "BTC > $100k by EOY"
        mock_position.tokenName = "YES"
        mock_position.avgPrice = 0.65
        mock_position.currentPrice = 0.75
        mock_position.shares = 5000.0
        mock_position.unrealizedPnl = 500.0
        mock_position.realizedPnl = 100.0

        # Mock generate_card_for_user to return a path
        mock_generate_card.return_value = Path("/output/card.png")

        result = await generate_card_for_position(
            bot=mock_bot,
            user=mock_user,
            position=mock_position
        )

        # Verify generate_card_for_user was called with extracted position data
        mock_generate_card.assert_called_once()
        call_kwargs = mock_generate_card.call_args[1]

        assert call_kwargs["bot"] == mock_bot
        assert call_kwargs["user"] == mock_user
        assert call_kwargs["market"] == "BTC > $100k by EOY"
        assert call_kwargs["position_type"] == "YES"
        assert call_kwargs["pnl_amount"] == 600.0  # unrealized + realized
        assert call_kwargs["avg_price"] == 0.65
        assert call_kwargs["current_price"] == 0.75
        assert call_kwargs["shares"] == 5000.0

        # Verify result
        assert result == Path("/output/card.png")

    @pytest.mark.asyncio
    @patch('utils.telegram.generate_card_for_user')
    @pytest.mark.anyio
    async def test_generate_card_for_position_no_position(self, mock_generate_card):
        """Test with NO position."""
        mock_bot = AsyncMock()
        mock_user = MagicMock()

        mock_position = MagicMock()
        mock_position.marketTitle = "ETH > $5k"
        mock_position.tokenName = "NO"
        mock_position.avgPrice = 0.35
        mock_position.currentPrice = 0.25
        mock_position.shares = 3000.0
        mock_position.unrealizedPnl = -300.0
        mock_position.realizedPnl = 0.0

        mock_generate_card.return_value = Path("/output/no_card.png")

        await generate_card_for_position(
            bot=mock_bot,
            user=mock_user,
            position=mock_position
        )

        call_kwargs = mock_generate_card.call_args[1]
        assert call_kwargs["position_type"] == "NO"
        assert call_kwargs["pnl_amount"] == -300.0

    @pytest.mark.asyncio
    @patch('utils.telegram.generate_card_for_user')
    @pytest.mark.anyio
    async def test_generate_card_for_position_zero_pnl(self, mock_generate_card):
        """Test with zero PnL."""
        mock_bot = AsyncMock()
        mock_user = MagicMock()

        mock_position = MagicMock()
        mock_position.marketTitle = "Test Market"
        mock_position.tokenName = "YES"
        mock_position.avgPrice = 0.5
        mock_position.currentPrice = 0.5
        mock_position.shares = 1000.0
        mock_position.unrealizedPnl = 0.0
        mock_position.realizedPnl = 0.0

        mock_generate_card.return_value = Path("/output/zero_pnl.png")

        await generate_card_for_position(
            bot=mock_bot,
            user=mock_user,
            position=mock_position
        )

        call_kwargs = mock_generate_card.call_args[1]
        assert call_kwargs["pnl_amount"] == 0.0

    @pytest.mark.asyncio
    @patch('utils.telegram.generate_card_for_user')
    @pytest.mark.anyio
    async def test_generate_card_for_position_combines_pnl(self, mock_generate_card):
        """Test that realized and unrealized PnL are combined."""
        mock_bot = AsyncMock()
        mock_user = MagicMock()

        mock_position = MagicMock()
        mock_position.marketTitle = "Combined PnL Test"
        mock_position.tokenName = "YES"
        mock_position.avgPrice = 0.4
        mock_position.currentPrice = 0.8
        mock_position.shares = 2500.0
        mock_position.unrealizedPnl = 1000.0
        mock_position.realizedPnl = 250.0

        mock_generate_card.return_value = Path("/output/combined.png")

        await generate_card_for_position(
            bot=mock_bot,
            user=mock_user,
            position=mock_position
        )

        call_kwargs = mock_generate_card.call_args[1]
        # Should combine both PnL values
        assert call_kwargs["pnl_amount"] == 1250.0


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for combined functionality."""

    @pytest.mark.asyncio
    @patch('utils.telegram.download_user_profile_pic')
    @patch('utils.telegram.TradingCard')
    @pytest.mark.anyio
    async def test_full_card_generation_flow(self, mock_card_class, mock_download):
        """Test complete card generation flow."""
        # Setup
        mock_bot = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = 55555
        mock_user.username = "fulltest"

        mock_position = MagicMock()
        mock_position.marketTitle = "Full Integration Test"
        mock_position.tokenName = "YES"
        mock_position.avgPrice = 0.55
        mock_position.currentPrice = 0.85
        mock_position.shares = 10000.0
        mock_position.unrealizedPnl = 3000.0
        mock_position.realizedPnl = 500.0

        mock_download.return_value = Path("/tmp/55555.jpg")
        mock_card = MagicMock()
        mock_card_class.return_value = mock_card

        # Execute
        with patch('pathlib.Path.mkdir'):
            result = await generate_card_for_position(
                bot=mock_bot,
                user=mock_user,
                position=mock_position
            )

        # Verify complete flow
        mock_download.assert_called_once_with(mock_bot, 55555)

        call_kwargs = mock_card_class.call_args[1]
        assert call_kwargs["username"] == "fulltest"
        assert call_kwargs["market"] == "Full Integration Test"
        assert call_kwargs["position_type"] == "YES"
        assert call_kwargs["pnl_amount"] == 3500.0
        assert call_kwargs["avg_price"] == 0.55
        assert call_kwargs["current_price"] == 0.85
        assert call_kwargs["shares"] == 10000.0
        assert call_kwargs["user_icon_path"] == "/tmp/55555.jpg"

        mock_card.save.assert_called_once()
        assert isinstance(result, Path)


# ============================================================================
# Test Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    @patch('utils.telegram.download_user_profile_pic')
    @pytest.mark.anyio
    async def test_download_with_zero_user_id(self, mock_download):
        """Test download with unusual user ID."""
        mock_bot = AsyncMock()

        mock_photos = MagicMock()
        mock_photos.total_count = 0
        mock_photos.photos = []
        mock_bot.get_user_profile_photos.return_value = mock_photos

        with patch('pathlib.Path.mkdir'):
            result = await download_user_profile_pic(mock_bot, 0)

        # Should handle gracefully
        assert result is None

    def test_get_display_name_with_none_values(self):
        """Test get_display_name with None values."""
        mock_user = MagicMock()
        mock_user.username = None
        mock_user.first_name = None

        # Should not crash, returns None
        name = get_display_name(mock_user)
        assert name is None

    @pytest.mark.asyncio
    @patch('utils.telegram.download_user_profile_pic')
    @patch('utils.telegram.TradingCard')
    @pytest.mark.anyio
    async def test_generate_card_with_very_long_market_name(self, mock_card_class, mock_download):
        """Test card generation with very long market name."""
        mock_bot = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = 77777
        mock_user.username = "test"

        mock_download.return_value = None
        mock_card = MagicMock()
        mock_card_class.return_value = mock_card

        very_long_market = "A" * 200  # Very long market name

        with patch('pathlib.Path.mkdir'):
            await generate_card_for_user(
                bot=mock_bot,
                user=mock_user,
                market=very_long_market,
                position_type="YES",
                pnl_amount=100.0,
                avg_price=0.5,
                current_price=0.6,
                shares=1000.0
            )

        # Should handle without error
        call_kwargs = mock_card_class.call_args[1]
        assert call_kwargs["market"] == very_long_market


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
