"""
Comprehensive unit tests for card.py

Tests all functions and classes in the card generation module using pytest.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, mock_open
from PIL import Image, ImageFont, ImageDraw
import sys
import random

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import card
from utils.card import (
    format_with_commas,
    measure_text_width,
    select_oneliner,
    TradingCard,
    PositionsCard,
    PnLHistoryCard,
    GREEN_ONELINERS,
    RED_ONELINERS,
    WIDTH,
    HEIGHT,
    BLACK,
    WHITE,
    GREEN,
    RED,
    GRAY,
    DEFAULT_BG
)


# ============================================================================
# Test Utility Functions
# ============================================================================

class TestFormatWithCommas:
    """Test format_with_commas function."""

    def test_format_small_number_no_commas(self):
        """Numbers < 1000 should not have commas."""
        assert format_with_commas(999.99, 2) == "999.99"
        assert format_with_commas(100.5, 2) == "100.50"
        assert format_with_commas(1.23, 2) == "1.23"

    def test_format_large_number_with_commas(self):
        """Numbers >= 1000 should have commas."""
        assert format_with_commas(1000.00, 2) == "1,000.00"
        assert format_with_commas(12345.67, 2) == "12,345.67"
        assert format_with_commas(1234567.89, 2) == "1,234,567.89"

    def test_format_zero_decimals(self):
        """Test formatting with zero decimal places."""
        assert format_with_commas(1234, 0) == "1,234"
        assert format_with_commas(999, 0) == "999"
        assert format_with_commas(5000.99, 0) == "5,000"

    def test_format_three_decimals(self):
        """Test formatting with three decimal places."""
        assert format_with_commas(0.123, 3) == "0.123"
        assert format_with_commas(999.456, 3) == "999.456"
        assert format_with_commas(1234.567, 3) == "1,234.567"

    def test_format_edge_cases(self):
        """Test edge cases like exactly 1000."""
        assert format_with_commas(1000, 0) == "1,000"
        assert format_with_commas(999.99, 0) == "999"
        assert format_with_commas(1000.01, 2) == "1,000.01"

    def test_format_very_large_numbers(self):
        """Test very large numbers."""
        assert format_with_commas(1000000, 2) == "1,000,000.00"
        assert format_with_commas(123456789.12, 2) == "123,456,789.12"


class TestMeasureTextWidth:
    """Test measure_text_width function."""

    @patch('utils.card.ImageFont.truetype')
    def test_measure_text_width_basic(self, mock_font_class):
        """Test basic text width measurement."""
        # Mock font and its getbbox method
        mock_font = MagicMock()
        mock_font.getbbox.return_value = (0, 0, 100, 20)  # left, top, right, bottom
        mock_font_class.return_value = mock_font

        width = measure_text_width("Hello", mock_font)
        assert width == 100

    @patch('utils.card.ImageFont.truetype')
    def test_measure_text_width_empty_string(self, mock_font_class):
        """Test measuring empty string."""
        mock_font = MagicMock()
        mock_font.getbbox.return_value = (0, 0, 0, 0)
        mock_font_class.return_value = mock_font

        width = measure_text_width("", mock_font)
        assert width == 0

    @patch('utils.card.ImageFont.truetype')
    def test_measure_text_width_negative_bbox(self, mock_font_class):
        """Test with negative bbox values (some fonts have negative left values)."""
        mock_font = MagicMock()
        mock_font.getbbox.return_value = (-5, -10, 95, 20)
        mock_font_class.return_value = mock_font

        width = measure_text_width("Text", mock_font)
        assert width == 100  # 95 - (-5)


class TestSelectOneliner:
    """Test select_oneliner function."""

    def test_select_green_oneliner_for_profit(self):
        """Positive PnL should select from GREEN_ONELINERS."""
        random.seed(42)  # Set seed for reproducible tests
        result = select_oneliner("user", 100.0)
        assert result in GREEN_ONELINERS

    def test_select_red_oneliner_for_loss(self):
        """Negative PnL should select from RED_ONELINERS."""
        random.seed(42)
        result = select_oneliner("user", -100.0)
        assert result in RED_ONELINERS

    def test_select_green_oneliner_for_zero(self):
        """Zero PnL should select from GREEN_ONELINERS."""
        random.seed(42)
        result = select_oneliner("user", 0.0)
        assert result in GREEN_ONELINERS

    def test_select_oneliner_username_unused(self):
        """Username parameter is unused but should not cause errors."""
        result1 = select_oneliner("Alice", 50.0)
        result2 = select_oneliner("Bob", 50.0)
        # Both should return valid oneliners
        assert result1 in GREEN_ONELINERS
        assert result2 in GREEN_ONELINERS

    def test_select_oneliner_randomness(self):
        """Test that different calls can return different oneliners."""
        results = set()
        for _ in range(20):
            results.add(select_oneliner("user", 100.0))
        # Should get some variety (though might not be all unique)
        assert len(results) >= 1


# ============================================================================
# Test TradingCard Class
# ============================================================================

class TestTradingCardInit:
    """Test TradingCard initialization."""

    def test_init_with_all_params(self):
        """Test initialization with all parameters."""
        card = TradingCard(
            username="Alice",
            market="BTC > $100k",
            position_type="YES",
            pnl_amount=1000.0,
            avg_price=0.65,
            current_price=0.75,
            shares=5000.0,
            background_path="/path/to/bg.png",
            user_icon_path="/path/to/icon.png"
        )

        assert card.username == "Alice"
        assert card.market == "BTC > $100k"
        assert card.position_type == "YES"
        assert card.pnl_amount == 1000.0
        assert card.avg_price == 0.65
        assert card.current_price == 0.75
        assert card.shares == 5000.0
        assert card.background_path == "/path/to/bg.png"
        assert card.user_icon_path == "/path/to/icon.png"

    def test_init_with_minimal_params(self):
        """Test initialization with minimal required parameters."""
        card = TradingCard(
            username="Bob",
            market="ETH > $5k",
            position_type="NO",
            pnl_amount=-500.0,
            avg_price=0.45,
            current_price=0.35,
            shares=2000.0
        )

        assert card.username == "Bob"
        assert card.background_path is None
        assert card.user_icon_path is None

    def test_new_classmethod(self):
        """Test .new() class method."""
        card = TradingCard.new(
            username="Charlie",
            market="SOL flips ETH",
            position_type="YES",
            pnl_amount=2500.0,
            avg_price=0.52,
            current_price=0.82,
            shares=10000.0
        )

        assert card.username == "Charlie"
        assert card.market == "SOL flips ETH"
        assert card.background_path is None
        assert card.user_icon_path is None

    def test_new_with_user_icon_classmethod(self):
        """Test .new_with_user_icon() class method."""
        card = TradingCard.new_with_user_icon(
            username="Diana",
            market="AI beats humans",
            position_type="NO",
            pnl_amount=750.0,
            avg_price=0.33,
            current_price=0.50,
            shares=3000.0,
            user_icon_path="diana.jpg"
        )

        assert card.username == "Diana"
        assert card.user_icon_path == "diana.jpg"
        assert card.background_path is None

    def test_with_background_method(self):
        """Test .with_background() method."""
        card = TradingCard.new(
            username="Eve",
            market="Test Market",
            position_type="YES",
            pnl_amount=100.0,
            avg_price=0.5,
            current_price=0.6,
            shares=1000.0
        )

        result = card.with_background("/path/to/custom_bg.png")

        assert result is card  # Should return self
        assert card.background_path == "/path/to/custom_bg.png"


class TestTradingCardUploadBackground:
    """Test TradingCard.upload_background static method."""

    @patch('utils.card.Image.open')
    @patch('utils.card.Path.cwd')
    def test_upload_background_success(self, mock_cwd, mock_image_open):
        """Test successful background upload."""
        mock_cwd.return_value = Path("/fake/project")
        mock_img = MagicMock()
        mock_image_open.return_value = mock_img

        with patch('builtins.print') as mock_print:
            TradingCard.upload_background("/source/image.png")

        mock_image_open.assert_called_once_with("/source/image.png")
        mock_img.save.assert_called_once()
        mock_print.assert_called_once()

    @patch('utils.card.Image.open')
    def test_upload_background_invalid_image(self, mock_image_open):
        """Test upload with invalid image file."""
        mock_image_open.side_effect = Exception("Invalid image")

        with pytest.raises(Exception, match="Invalid image"):
            TradingCard.upload_background("/invalid/path.txt")


class TestTradingCardGenerateImage:
    """Test TradingCard.generate_image method."""

    @patch('utils.card.Image.open')
    @patch('utils.card.Path.cwd')
    @patch('utils.card.ImageFont.truetype')
    def test_generate_image_with_default_background(self, mock_font, mock_cwd, mock_image_open):
        """Test image generation with default background."""
        mock_cwd.return_value = Path("/fake/project")

        # Mock background image
        mock_bg = MagicMock(spec=Image.Image)
        mock_bg.convert.return_value = mock_bg
        mock_bg.resize.return_value = mock_bg
        mock_image_open.return_value = mock_bg

        # Mock font
        mock_font.return_value = MagicMock()

        card = TradingCard.new(
            username="Test",
            market="Test Market",
            position_type="YES",
            pnl_amount=1000.0,
            avg_price=0.5,
            current_price=0.7,
            shares=5000.0
        )

        with patch.object(card, 'draw_branding'), \
             patch.object(card, 'draw_pnl'), \
             patch.object(card, 'draw_position_info'), \
             patch.object(card, 'draw_stats'):

            img = card.generate_image()

        assert img is not None
        mock_bg.resize.assert_called_once_with((WIDTH, HEIGHT), Image.Resampling.LANCZOS)

    @patch('utils.card.Image.new')
    @patch('utils.card.Image.open')
    @patch('utils.card.Path.cwd')
    @patch('utils.card.ImageFont.truetype')
    def test_generate_image_fallback_on_missing_background(self, mock_font, mock_cwd, mock_image_open, mock_image_new):
        """Test fallback to solid color when background not found."""
        mock_cwd.return_value = Path("/fake/project")
        mock_image_open.side_effect = Exception("File not found")

        # Mock new solid background
        mock_solid_bg = MagicMock(spec=Image.Image)
        mock_image_new.return_value = mock_solid_bg
        mock_font.return_value = MagicMock()

        card = TradingCard.new(
            username="Test",
            market="Test",
            position_type="YES",
            pnl_amount=100.0,
            avg_price=0.5,
            current_price=0.6,
            shares=1000.0
        )

        with patch.object(card, 'draw_branding'), \
             patch.object(card, 'draw_pnl'), \
             patch.object(card, 'draw_position_info'), \
             patch.object(card, 'draw_stats'):

            img = card.generate_image()

        mock_image_new.assert_called_once_with("RGBA", (WIDTH, HEIGHT), DEFAULT_BG)


class TestTradingCardSave:
    """Test TradingCard.save method."""

    @patch.object(TradingCard, 'generate_image')
    def test_save_success(self, mock_generate):
        """Test successful card save."""
        mock_img = MagicMock()
        mock_generate.return_value = mock_img

        card = TradingCard.new(
            username="Test",
            market="Test",
            position_type="YES",
            pnl_amount=100.0,
            avg_price=0.5,
            current_price=0.6,
            shares=1000.0
        )

        card.save("/output/path.png")

        mock_generate.assert_called_once()
        mock_img.save.assert_called_once_with("/output/path.png")


# ============================================================================
# Test PositionsCard Class
# ============================================================================

class TestPositionsCardInit:
    """Test PositionsCard initialization."""

    def test_init_with_all_params(self):
        """Test initialization with all parameters."""
        positions = [
            {"market": "BTC > $100k", "side": "YES", "shares": 5000,
             "avg_price": 0.65, "current_price": 0.75, "pnl": 500}
        ]

        card = PositionsCard(
            username="Alice",
            total_value=10000.0,
            total_pnl=500.0,
            positions=positions,
            user_icon_path="alice.jpg",
            background_path="bg.png"
        )

        assert card.username == "Alice"
        assert card.total_value == 10000.0
        assert card.total_pnl == 500.0
        assert len(card.positions) == 1
        assert card.user_icon_path == "alice.jpg"
        assert card.background_path == "bg.png"

    def test_init_limits_positions_to_six(self):
        """Test that positions are limited to 6."""
        positions = [
            {"market": f"Market {i}", "side": "YES", "shares": 1000,
             "avg_price": 0.5, "current_price": 0.6, "pnl": 100}
            for i in range(10)
        ]

        card = PositionsCard(
            username="Bob",
            total_value=5000.0,
            total_pnl=1000.0,
            positions=positions
        )

        assert len(card.positions) == 6

    def test_new_classmethod(self):
        """Test .new() class method."""
        positions = [{"market": "Test", "side": "NO", "shares": 2000,
                      "avg_price": 0.4, "current_price": 0.3, "pnl": -200}]

        card = PositionsCard.new(
            username="Charlie",
            total_value=3000.0,
            total_pnl=-200.0,
            positions=positions
        )

        assert card.username == "Charlie"
        assert card.user_icon_path is None
        assert card.background_path is None

    def test_new_with_user_icon_classmethod(self):
        """Test .new_with_user_icon() class method."""
        positions = []
        card = PositionsCard.new_with_user_icon(
            username="Diana",
            total_value=1000.0,
            total_pnl=50.0,
            positions=positions,
            user_icon_path="diana.jpg"
        )

        assert card.user_icon_path == "diana.jpg"


class TestPositionsCardGenerateImage:
    """Test PositionsCard.generate_image method."""

    @patch('utils.card.Image.open')
    @patch('utils.card.Path.cwd')
    @patch('utils.card.ImageFont.truetype')
    def test_generate_image_basic(self, mock_font, mock_cwd, mock_image_open):
        """Test basic image generation."""
        mock_cwd.return_value = Path("/fake/project")

        mock_bg = MagicMock(spec=Image.Image)
        mock_bg.convert.return_value = mock_bg
        mock_bg.resize.return_value = mock_bg
        mock_image_open.return_value = mock_bg
        mock_font.return_value = MagicMock()

        positions = [
            {"market": "Test", "side": "YES", "shares": 1000,
             "avg_price": 0.5, "current_price": 0.6, "pnl": 100}
        ]

        card = PositionsCard.new(
            username="Test",
            total_value=1000.0,
            total_pnl=100.0,
            positions=positions
        )

        with patch.object(card, 'draw_header'), \
             patch.object(card, 'draw_total_stats'), \
             patch.object(card, 'draw_positions_table'):

            img = card.generate_image()

        assert img is not None


# ============================================================================
# Test PnLHistoryCard Class
# ============================================================================

class TestPnLHistoryCardInit:
    """Test PnLHistoryCard initialization."""

    def test_init_with_valid_timeframe(self):
        """Test initialization with valid timeframe."""
        pnl_data = [
            {"timestamp": 1000, "pnl": 100},
            {"timestamp": 2000, "pnl": 200},
            {"timestamp": 3000, "pnl": 300}
        ]

        card = PnLHistoryCard(
            username="Alice",
            pnl_data=pnl_data,
            timeframe="1W"
        )

        assert card.username == "Alice"
        assert card.timeframe == "1W"
        assert len(card.pnl_data) == 3
        assert card.start_pnl == 100
        assert card.end_pnl == 300
        assert card.change == 200
        assert card.max_pnl == 300
        assert card.min_pnl == 100

    def test_init_with_invalid_timeframe(self):
        """Test initialization with invalid timeframe raises error."""
        pnl_data = [{"timestamp": 1000, "pnl": 100}]

        with pytest.raises(ValueError, match="Timeframe must be one of"):
            PnLHistoryCard(
                username="Bob",
                pnl_data=pnl_data,
                timeframe="INVALID"
            )

    def test_init_sorts_pnl_data_by_timestamp(self):
        """Test that PnL data is sorted by timestamp."""
        pnl_data = [
            {"timestamp": 3000, "pnl": 300},
            {"timestamp": 1000, "pnl": 100},
            {"timestamp": 2000, "pnl": 200}
        ]

        card = PnLHistoryCard(
            username="Charlie",
            pnl_data=pnl_data,
            timeframe="1D"
        )

        assert card.pnl_data[0]["timestamp"] == 1000
        assert card.pnl_data[1]["timestamp"] == 2000
        assert card.pnl_data[2]["timestamp"] == 3000

    def test_init_with_empty_data(self):
        """Test initialization with empty PnL data."""
        card = PnLHistoryCard(
            username="Diana",
            pnl_data=[],
            timeframe="1M"
        )

        assert card.start_pnl == 0
        assert card.end_pnl == 0
        assert card.change == 0
        assert card.max_pnl == 0
        assert card.min_pnl == 0

    def test_new_classmethod(self):
        """Test .new() class method."""
        pnl_data = [{"timestamp": 1000, "pnl": 50}]

        card = PnLHistoryCard.new(
            username="Eve",
            pnl_data=pnl_data,
            timeframe="ALL"
        )

        assert card.username == "Eve"
        assert card.timeframe == "ALL"

    def test_new_with_user_icon_classmethod(self):
        """Test .new_with_user_icon() class method."""
        pnl_data = [{"timestamp": 1000, "pnl": 75}]

        card = PnLHistoryCard.new_with_user_icon(
            username="Frank",
            pnl_data=pnl_data,
            timeframe="1D",
            user_icon_path="frank.jpg"
        )

        assert card.user_icon_path == "frank.jpg"

    def test_valid_timeframes(self):
        """Test all valid timeframes."""
        pnl_data = [{"timestamp": 1000, "pnl": 100}]
        valid_timeframes = ["1D", "1W", "1M", "ALL"]

        for tf in valid_timeframes:
            card = PnLHistoryCard(
                username="Test",
                pnl_data=pnl_data,
                timeframe=tf
            )
            assert card.timeframe == tf


class TestPnLHistoryCardGenerateImage:
    """Test PnLHistoryCard.generate_image method."""

    @patch('utils.card.Image.open')
    @patch('utils.card.Path.cwd')
    @patch('utils.card.ImageFont.truetype')
    def test_generate_image_with_data(self, mock_font, mock_cwd, mock_image_open):
        """Test image generation with PnL data."""
        mock_cwd.return_value = Path("/fake/project")

        mock_bg = MagicMock(spec=Image.Image)
        mock_bg.convert.return_value = mock_bg
        mock_bg.resize.return_value = mock_bg
        mock_image_open.return_value = mock_bg
        mock_font.return_value = MagicMock()

        pnl_data = [
            {"timestamp": 1000, "pnl": 100},
            {"timestamp": 2000, "pnl": 200},
            {"timestamp": 3000, "pnl": 150}
        ]

        card = PnLHistoryCard.new(
            username="Test",
            pnl_data=pnl_data,
            timeframe="1W"
        )

        with patch.object(card, 'draw_header'), \
             patch.object(card, 'draw_stats'), \
             patch.object(card, 'draw_graph'):

            img = card.generate_image()

        assert img is not None

    @patch('utils.card.Image.open')
    @patch('utils.card.Path.cwd')
    @patch('utils.card.ImageFont.truetype')
    @patch('utils.card.ImageDraw.Draw')
    def test_generate_image_insufficient_data(self, mock_draw, mock_font, mock_cwd, mock_image_open):
        """Test image generation with insufficient data for graph."""
        mock_cwd.return_value = Path("/fake/project")

        mock_bg = MagicMock(spec=Image.Image)
        mock_bg.convert.return_value = mock_bg
        mock_bg.resize.return_value = mock_bg
        mock_image_open.return_value = mock_bg
        mock_font.return_value = MagicMock()
        mock_draw.return_value = MagicMock()

        pnl_data = [{"timestamp": 1000, "pnl": 100}]  # Only one point

        card = PnLHistoryCard.new(
            username="Test",
            pnl_data=pnl_data,
            timeframe="1D"
        )

        with patch.object(card, 'draw_header'), \
             patch.object(card, 'draw_stats'):

            img = card.generate_image()

        assert img is not None


class TestPnLHistoryCardSave:
    """Test PnLHistoryCard.save method."""

    @patch.object(PnLHistoryCard, 'generate_image')
    def test_save_success(self, mock_generate):
        """Test successful save."""
        mock_img = MagicMock()
        mock_generate.return_value = mock_img

        pnl_data = [{"timestamp": 1000, "pnl": 100}]
        card = PnLHistoryCard.new(
            username="Test",
            pnl_data=pnl_data,
            timeframe="1W"
        )

        card.save("/output/pnl_history.png")

        mock_generate.assert_called_once()
        mock_img.save.assert_called_once_with("/output/pnl_history.png")


# ============================================================================
# Test Constants
# ============================================================================

class TestConstants:
    """Test module constants."""

    def test_card_dimensions(self):
        """Test card dimensions are defined."""
        assert WIDTH == 822
        assert HEIGHT == 474

    def test_color_constants(self):
        """Test color constants are RGBA tuples."""
        assert BLACK == (0, 0, 0, 255)
        assert WHITE == (255, 255, 255, 255)
        assert GREEN == (34, 197, 94, 255)
        assert RED == (239, 68, 68, 255)
        assert GRAY == (156, 163, 175, 255)
        assert DEFAULT_BG == (0, 0, 0, 255)

    def test_oneliner_lists(self):
        """Test one-liner lists are not empty."""
        assert len(GREEN_ONELINERS) > 0
        assert len(RED_ONELINERS) > 0
        assert all(isinstance(line, str) for line in GREEN_ONELINERS)
        assert all(isinstance(line, str) for line in RED_ONELINERS)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
