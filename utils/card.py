"""
Trading Card Generator

Python conversion of card.rs using PIL (Pillow) as the equivalent of Rust's image crate.
"""

import random
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont


def format_with_commas(num: float, decimals: int) -> str:
    """
    Format numbers with commas and specified decimal places.
    Only adds commas for amounts >= 1,000.

    Args:
        num: Number to format (absolute value expected)
        decimals: Number of decimal places

    Returns:
        Formatted string with commas (for amounts >= 1000 only)
    """
    formatted = f"{num:.{decimals}f}"
    parts = formatted.split('.')
    int_part = parts[0]
    dec_part = parts[1] if len(parts) > 1 else ""

    # Only add commas if the integer part is >= 1000
    if len(int_part) >= 4:
        result = ""
        chars = list(int_part)
        length = len(chars)

        for i, c in enumerate(chars):
            if i > 0 and (length - i) % 3 == 0:
                result += ','
            result += c
    else:
        result = int_part

    if decimals > 0 and dec_part:
        result += '.'
        result += dec_part

    return result


def measure_text_width(text: str, font: ImageFont.FreeTypeFont) -> float:
    """
    Measure text width dynamically.

    Args:
        text: Text to measure
        font: Font to use for measurement

    Returns:
        Width in pixels
    """
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


# Card dimensions
WIDTH = 822
HEIGHT = 474

# Colors (RGBA tuples)
BLACK = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)
GREEN = (34, 197, 94, 255)  # Modern green
RED = (239, 68, 68, 255)    # Modern red
GRAY = (156, 163, 175, 255)  # Light gray for labels (deprecated)
DEFAULT_BG = (0, 0, 0, 255)  # #000000

# Green PnL one-liners
GREEN_ONELINERS = [
    "Locked in.",
    "On the road to generational wealth.",
    "We are so back.",
    "Consider me diversified (emotionally).",
    "Print go brrr.",
    "Number go up technology.",
    "Cooked perfectly.",
    "Pillow made of realized gains.",
    "Protagonist arc unlocked.",
    "Uncle Sam is smiling.",
]

# Red PnL one-liners
RED_ONELINERS = [
    "Back to ramen.",
    "Long on hope, short on discipline.",
    "Risk managed me.",
    "Portfolio doing the limbo.",
    "I believed, the market did not.",
    "Invented negative momentum.",
    "Positions reduced... by gravity.",
    "It's only down if you look.",
    "Stop-loss? More like stop-lost.",
    "Chart looks like my feelings.",
]


def select_oneliner(username: str, pnl: float) -> str:
    """
    Select a one-liner randomly based on PnL.

    Args:
        username: User's name (unused, kept for compatibility)
        pnl: Profit/Loss amount

    Returns:
        Random one-liner string
    """
    oneliners = GREEN_ONELINERS if pnl >= 0.0 else RED_ONELINERS
    return random.choice(oneliners)


class TradingCard:
    """
    Generate trading card images for sharing positions.

    This is a direct Python conversion of the Rust TradingCard struct.
    """

    def __init__(
        self,
        username: str,
        market: str,
        position_type: str,
        pnl_amount: float,
        avg_price: float,
        current_price: float,
        shares: float,
        background_path: Optional[str] = None,
        user_icon_path: Optional[str] = None,
    ):
        """
        Initialize a TradingCard for Polymarket prediction markets.

        Args:
            username: User's display name
            market: Market name/question (e.g., "BTC > $100k by EOY")
            position_type: "YES" or "NO"
            pnl_amount: Profit/Loss amount in dollars
            avg_price: Average entry price (0.0-1.0)
            current_price: Current market price (0.0-1.0)
            shares: Number of outcome token shares held
            background_path: Optional custom background image path
            user_icon_path: Optional user profile picture path
        """
        self.username = username
        self.market = market
        self.position_type = position_type
        self.pnl_amount = pnl_amount
        self.avg_price = avg_price
        self.current_price = current_price
        self.shares = shares
        self.background_path = background_path
        self.user_icon_path = user_icon_path

    @classmethod
    def new(
        cls,
        username: str,
        market: str,
        position_type: str,
        pnl_amount: float,
        avg_price: float,
        current_price: float,
        shares: float,
    ) -> "TradingCard":
        """Create a new TradingCard for Polymarket prediction markets."""
        return cls(
            username=username,
            market=market,
            position_type=position_type,
            pnl_amount=pnl_amount,
            avg_price=avg_price,
            current_price=current_price,
            shares=shares,
        )

    @classmethod
    def new_with_user_icon(
        cls,
        username: str,
        market: str,
        position_type: str,
        pnl_amount: float,
        avg_price: float,
        current_price: float,
        shares: float,
        user_icon_path: str,
    ) -> "TradingCard":
        """Create a trading card with a custom user icon (e.g., Telegram profile picture)."""
        return cls(
            username=username,
            market=market,
            position_type=position_type,
            pnl_amount=pnl_amount,
            avg_price=avg_price,
            current_price=current_price,
            shares=shares,
            user_icon_path=user_icon_path,
        )

    def with_background(self, path: str) -> "TradingCard":
        """Set a custom background image for the trading card."""
        self.background_path = path
        return self

    @staticmethod
    def upload_background(source_path: str) -> None:
        """
        Upload and set a background image from a file path.
        This copies the image to the project directory as card-background.png.

        Args:
            source_path: Path to source image file

        Raises:
            Exception: If image cannot be loaded or saved
        """
        project_root = Path.cwd()
        dest_path = project_root / "card-background.png"

        # Load the image to validate it's a valid image file
        img = Image.open(source_path)

        # Save it to the project directory
        img.save(dest_path)

        print(f"Background image uploaded successfully to: {dest_path}")

    def generate_image(self) -> Image.Image:
        """
        Generate the trading card image.

        Returns:
            PIL Image object
        """
        project_root = Path.cwd()

        # Use custom background if provided, otherwise use default from assets
        if self.background_path:
            background_to_load = self.background_path
        else:
            # Default background from assets
            background_to_load = str(project_root / "assets" / "card-background.png")

        try:
            img = Image.open(background_to_load).convert("RGBA")
            # Resize background to match card dimensions
            img = img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        except Exception as e:
            print(f"Failed to load background image: {e}")
            # Fallback to solid color if background not found
            img = Image.new("RGBA", (WIDTH, HEIGHT), DEFAULT_BG)

        # Load font - using type_writer
        project_root = Path.cwd()
        font_path = project_root / "assets" / "type_writer.ttf"

        try:
            font_data = font_path.read_bytes()
            # Font will be loaded per size as needed
        except Exception as e:
            print(f"Failed to read font file: {e}")
            raise

        # Draw branding in top left
        self.draw_branding(img, font_path)

        # Draw main PnL display
        self.draw_pnl(img, font_path)

        # Draw position details
        self.draw_position_info(img, font_path)

        # Draw bottom stats
        self.draw_stats(img, font_path)

        return img

    def draw_branding(self, img: Image.Image, font_path: Path):
        """Draw branding elements (user icon and username)."""
        draw = ImageDraw.Draw(img)

        # Load and draw user icon on left
        project_root = Path.cwd()
        polymarket_path = project_root / "assets" / "polymarket-icon.png"

        icon_size = 50
        brand_x = 35
        brand_y = 30

        # Draw user icon - use custom user icon if provided, otherwise use polymarket icon
        # If user_icon_path is provided, check if it's absolute or relative
        if self.user_icon_path:
            user_icon = Path(self.user_icon_path)
            # If it's not absolute, assume it's in assets/
            if not user_icon.is_absolute():
                icon_path = project_root / "assets" / self.user_icon_path
            else:
                icon_path = user_icon
        else:
            icon_path = polymarket_path

        try:
            user_img = Image.open(icon_path).convert("RGBA")
            user_resized = user_img.resize((icon_size, icon_size), Image.Resampling.LANCZOS)

            icon_x = brand_x
            icon_y = brand_y
            radius = icon_size / 2
            center_x = icon_x + radius
            center_y = icon_y + radius

            # Create circular mask
            mask = Image.new("L", (icon_size, icon_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse([0, 0, icon_size, icon_size], fill=255)

            # Apply circular mask and paste
            img.paste(user_resized, (icon_x, icon_y), mask)
        except Exception:
            pass  # Skip if icon not found

        # Draw username in uppercase next to icon (vertically centered) with more spacing
        font_28 = ImageFont.truetype(str(font_path), 28)
        text_height = 28
        text_y = brand_y + (icon_size - text_height) // 2
        draw.text(
            (brand_x + icon_size + 20, text_y),
            self.username.upper(),
            fill=WHITE,
            font=font_28
        )

        # Draw polymarket icon next to "OPIATE" in top right (aligned with left branding)
        polymarket_right_size = 70  # Enlarged from 50
        brand_right_x = WIDTH - 165  # Adjusted for "OPIATE" width

        # Draw polymarket icon on right (much closer to text)
        try:
            polymarket_img = Image.open(polymarket_path).convert("RGBA")
            polymarket_resized = polymarket_img.resize((polymarket_right_size, polymarket_right_size), Image.Resampling.LANCZOS)

            # Position much closer to OPIATE text - minimal spacing
            polymarket_x = brand_right_x - 78  # Much closer spacing
            # Vertically align center of icon with center of username text
            text_center_y = brand_y + (icon_size // 2)
            polymarket_y = text_center_y - (polymarket_right_size // 2)

            img.paste(polymarket_resized, (polymarket_x, polymarket_y), polymarket_resized)
        except Exception:
            pass  # Skip if polymarket icon not found

        # Draw "OPIATE" text (vertically centered with username)
        brand_text_height = 28
        brand_text_y = brand_y + (icon_size - brand_text_height) // 2  # Align with username center
        draw.text(
            (brand_right_x, brand_text_y),
            "OPIATE",
            fill=WHITE,
            font=font_28
        )

    def draw_pnl(self, img: Image.Image, font_path: Path):
        """Draw the main PnL display."""
        draw = ImageDraw.Draw(img)

        pnl_color = GREEN if self.pnl_amount >= 0.0 else RED

        # Draw market name and position badge
        badge_height = 30
        badge_y = 116

        # Draw market name (truncated if too long)
        font_20 = ImageFont.truetype(str(font_path), 20)
        market_display = self.market[:35] + "..." if len(self.market) > 35 else self.market
        market_text_height = 20
        market_y = badge_y + (badge_height - market_text_height) // 2
        draw.text((40, market_y), market_display, fill=WHITE, font=font_20)

        # Draw position badge (YES or NO)
        badge_text = self.position_type.upper()
        font_16 = ImageFont.truetype(str(font_path), 16)

        # Badge color: GREEN for YES, RED for NO
        badge_color = GREEN if self.position_type.upper() == "YES" else RED

        # Dynamically measure market width to position badge properly
        market_width = measure_text_width(market_display, font_20)
        badge_x = 40 + int(market_width) + 15  # 15px spacing between market and badge

        # Dynamically measure text width for tighter fit
        text_width = measure_text_width(badge_text, font_16)
        badge_padding = 12  # Horizontal padding on each side
        badge_width = int(text_width) + (badge_padding * 2)
        badge_height = 26  # Slightly shorter height

        # Draw filled rectangle for badge
        draw.rectangle(
            [(badge_x, badge_y + 2), (badge_x + badge_width, badge_y + badge_height + 2)],
            fill=badge_color
        )

        # Center text both vertically and horizontally in badge
        badge_text_height = 16

        # Center horizontally using measured width
        text_x = badge_x + badge_padding

        # Center vertically
        text_y = badge_y + ((badge_height - badge_text_height) // 2) + 2

        draw.text((text_x, text_y), badge_text, fill=BLACK, font=font_16)

        # Draw PnL dollar amount (large)
        if self.pnl_amount >= 0.0:
            pnl_text = f"+${format_with_commas(self.pnl_amount, 2)}"
        else:
            pnl_text = f"-${format_with_commas(abs(self.pnl_amount), 2)}"

        font_60 = ImageFont.truetype(str(font_path), 60)
        draw.text((40, 175), pnl_text, fill=pnl_color, font=font_60)

    def draw_position_info(self, img: Image.Image, font_path: Path):
        """Draw position details."""
        draw = ImageDraw.Draw(img)

        y_start = 290
        font_16 = ImageFont.truetype(str(font_path), 16)
        font_22 = ImageFont.truetype(str(font_path), 22)

        # Average Price (prediction markets use 0.0-1.0 pricing)
        draw.text((40, y_start), "AVG PRICE", fill=WHITE, font=font_16)
        draw.text(
            (40, y_start + 24),
            f"${self.avg_price:.3f}",
            fill=WHITE,
            font=font_22
        )

        # Current Price
        draw.text((200, y_start), "CURRENT", fill=WHITE, font=font_16)
        draw.text(
            (200, y_start + 24),
            f"${self.current_price:.3f}",
            fill=WHITE,
            font=font_22
        )

        # Shares (number of outcome tokens)
        draw.text((370, y_start), "SHARES", fill=WHITE, font=font_16)
        draw.text(
            (370, y_start + 24),
            f"{format_with_commas(self.shares, 0)}",
            fill=WHITE,
            font=font_22
        )

    def draw_stats(self, img: Image.Image, font_path: Path):
        """Draw bottom stats with one-liner."""
        draw = ImageDraw.Draw(img)

        # Select and draw a funny one-liner based on PnL
        oneliner = select_oneliner(self.username, self.pnl_amount)
        font_16 = ImageFont.truetype(str(font_path), 16)
        draw.text(
            (40, HEIGHT - 30),
            oneliner,
            fill=WHITE,
            font=font_16
        )

    def save(self, path: str) -> None:
        """
        Save the trading card to a file.

        Args:
            path: Output file path

        Raises:
            Exception: If image cannot be saved
        """
        img = self.generate_image()
        img.save(path)


def main():
    """Test with Polymarket prediction market format"""
    card = TradingCard.new_with_user_icon(
        username="EON",
        market="BTC > $100k by EOY 2024",
        position_type="YES",
        pnl_amount=2500.0,       # PnL amount
        avg_price=0.65,          # Average entry price
        current_price=0.85,      # Current market price
        shares=5000.0,           # Number of shares
        user_icon_path="eon-icon.jpg",  # Will look in assets/
    )

    # Optional: Set custom background image (if file exists)
    # Uncomment the line below to use a custom background:
    card.background_path = "card-background.png"

    try:
        card.save("trading_card.png")
        print("Image generated successfully: trading_card.png")
    except Exception as e:
        print(f"Error generating image: {e}")

    # Example 2: NO position with loss
    # Uncomment the lines below to test:
    #
    # card_with_loss = TradingCard.new(
    #     username="alice",
    #     market="ETH > $5k by March 2024",
    #     position_type="NO",
    #     pnl_amount=-850.0,
    #     avg_price=0.45,
    #     current_price=0.25,
    #     shares=3000.0
    # ).with_background("card-background.png")
    #
    # card_with_loss.save("trading_card_loss.png")


class PositionsCard:
    """
    Generate positions overview card for prediction markets.
    Shows multiple positions in a table format.
    """

    def __init__(
        self,
        username: str,
        total_value: float,
        total_pnl: float,
        positions: list[dict],
        user_icon_path: Optional[str] = None,
        background_path: Optional[str] = None,
    ):
        """
        Initialize a PositionsCard.

        Args:
            username: User's display name
            total_value: Total portfolio value
            total_pnl: Total profit/loss across all positions
            positions: List of position dicts with keys:
                - market: Market name (truncated if needed)
                - side: "YES" or "NO"
                - shares: Number of shares
                - avg_price: Average entry price
                - current_price: Current market price
                - pnl: Position P&L
            user_icon_path: Optional user profile picture path
            background_path: Optional custom background image path
        """
        self.username = username
        self.total_value = total_value
        self.total_pnl = total_pnl
        self.positions = positions[:6]  # Limit to 6 positions for display
        self.user_icon_path = user_icon_path
        self.background_path = background_path

    @classmethod
    def new(
        cls,
        username: str,
        total_value: float,
        total_pnl: float,
        positions: list[dict],
    ) -> "PositionsCard":
        """Create a new PositionsCard."""
        return cls(
            username=username,
            total_value=total_value,
            total_pnl=total_pnl,
            positions=positions,
        )

    @classmethod
    def new_with_user_icon(
        cls,
        username: str,
        total_value: float,
        total_pnl: float,
        positions: list[dict],
        user_icon_path: str,
    ) -> "PositionsCard":
        """Create a positions card with a custom user icon."""
        return cls(
            username=username,
            total_value=total_value,
            total_pnl=total_pnl,
            positions=positions,
            user_icon_path=user_icon_path,
        )

    def generate_image(self) -> Image.Image:
        """Generate the positions card image."""
        project_root = Path.cwd()

        # Use custom background if provided, otherwise use default from assets
        if self.background_path:
            background_to_load = self.background_path
        else:
            # Default background from assets
            background_to_load = str(project_root / "assets" / "card-background.png")

        try:
            img = Image.open(background_to_load).convert("RGBA")
            img = img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        except Exception as e:
            print(f"Failed to load background image: {e}")
            # Fallback to solid color if background not found
            img = Image.new("RGBA", (WIDTH, HEIGHT), DEFAULT_BG)

        # Load font
        project_root = Path.cwd()
        font_path = project_root / "assets" / "type_writer.ttf"

        try:
            font_path.read_bytes()
        except Exception as e:
            print(f"Failed to read font file: {e}")
            raise

        # Draw all components
        self.draw_header(img, font_path)
        self.draw_total_stats(img, font_path)
        self.draw_positions_table(img, font_path)

        return img

    def draw_header(self, img: Image.Image, font_path: Path):
        """Draw header with user info and branding."""
        draw = ImageDraw.Draw(img)
        project_root = Path.cwd()
        polymarket_path = project_root / "assets" / "polymarket-icon.png"

        icon_size = 50
        brand_x = 35
        brand_y = 30

        # Draw user icon
        if self.user_icon_path:
            user_icon = Path(self.user_icon_path)
            if not user_icon.is_absolute():
                icon_path = project_root / "assets" / self.user_icon_path
            else:
                icon_path = user_icon
        else:
            icon_path = polymarket_path

        try:
            user_img = Image.open(icon_path).convert("RGBA")
            user_resized = user_img.resize((icon_size, icon_size), Image.Resampling.LANCZOS)

            # Create circular mask
            mask = Image.new("L", (icon_size, icon_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse([0, 0, icon_size, icon_size], fill=255)

            img.paste(user_resized, (brand_x, brand_y), mask)
        except Exception:
            pass

        # Draw username
        font_28 = ImageFont.truetype(str(font_path), 28)
        text_height = 28
        text_y = brand_y + (icon_size - text_height) // 2
        draw.text(
            (brand_x + icon_size + 20, text_y),
            self.username.upper(),
            fill=WHITE,
            font=font_28
        )

        # Draw polymarket branding on right
        brand_right_x = WIDTH - 165

        try:
            polymarket_img = Image.open(polymarket_path).convert("RGBA")
            polymarket_right_size = 70  # Enlarged from 50
            polymarket_resized = polymarket_img.resize((polymarket_right_size, polymarket_right_size), Image.Resampling.LANCZOS)
            # Position much closer to OPIATE text
            polymarket_x = brand_right_x - 78  # Much closer spacing
            # Vertically align center of icon with center of username text
            text_center_y = brand_y + (icon_size // 2)
            polymarket_y = text_center_y - (polymarket_right_size // 2)
            img.paste(polymarket_resized, (polymarket_x, polymarket_y), polymarket_resized)
        except Exception:
            pass

        brand_text_y = brand_y + (icon_size - 28) // 2
        draw.text(
            (brand_right_x, brand_text_y),
            "OPIATE",
            fill=WHITE,
            font=font_28
        )

    def draw_total_stats(self, img: Image.Image, font_path: Path):
        """Draw total portfolio value and PnL."""
        draw = ImageDraw.Draw(img)

        font_24 = ImageFont.truetype(str(font_path), 24)
        font_18 = ImageFont.truetype(str(font_path), 18)

        # Total portfolio value
        value_text = f"${format_with_commas(self.total_value, 2)}"
        draw.text((40, 110), value_text, fill=WHITE, font=font_24)

        # Total PnL with color
        pnl_color = GREEN if self.total_pnl >= 0.0 else RED
        if self.total_pnl >= 0.0:
            pnl_text = f"+${format_with_commas(self.total_pnl, 2)}"
        else:
            pnl_text = f"-${format_with_commas(abs(self.total_pnl), 2)}"

        # Position PnL next to total value
        value_width = measure_text_width(value_text, font_24)
        draw.text((40 + value_width + 20, 110), pnl_text, fill=pnl_color, font=font_24)

    def draw_positions_table(self, img: Image.Image, font_path: Path):
        """Draw positions table."""
        draw = ImageDraw.Draw(img)

        font_14 = ImageFont.truetype(str(font_path), 14)
        font_16 = ImageFont.truetype(str(font_path), 16)

        # Table headers
        table_y = 160
        header_y = table_y

        # Column positions - adjusted for prediction markets
        col_position = 40
        col_shares = 320
        col_avg = 420
        col_current = 540
        col_pnl = 680

        # Draw headers
        draw.text((col_position, header_y), "POSITION", fill=GRAY, font=font_14)
        draw.text((col_shares, header_y), "SHARES", fill=GRAY, font=font_14)
        draw.text((col_avg, header_y), "AVG", fill=GRAY, font=font_14)
        draw.text((col_current, header_y), "CURRENT", fill=GRAY, font=font_14)
        draw.text((col_pnl, header_y), "PNL", fill=GRAY, font=font_14)

        # Draw positions
        row_height = 40
        start_y = header_y + 35

        for i, pos in enumerate(self.positions):
            y = start_y + (i * row_height)

            # Truncate market name if too long
            market = pos.get("market", "Unknown")
            if len(market) > 20:
                market = market[:20] + "..."

            # Position side badge
            side = pos.get("side", "YES").upper()
            badge_color = GREEN if side == "YES" else RED

            # Draw position name
            draw.text((col_position, y), market, fill=WHITE, font=font_16)

            # Draw side badge next to market name (tighter fit)
            market_width = measure_text_width(market, font_16)
            badge_x = col_position + int(market_width) + 8

            # Measure text width for tight fit
            side_text_width = measure_text_width(side, font_14)
            badge_padding = 8  # Horizontal padding on each side
            badge_width = int(side_text_width) + (badge_padding * 2)
            badge_height = 18

            draw.rectangle(
                [(badge_x, y), (badge_x + badge_width, y + badge_height)],
                fill=badge_color
            )

            side_x = badge_x + badge_padding
            draw.text((side_x, y + 1), side, fill=BLACK, font=font_14)

            # Shares
            shares = pos.get("shares", 0)
            shares_text = format_with_commas(shares, 0)
            draw.text((col_shares, y), shares_text, fill=WHITE, font=font_16)

            # Avg price
            avg_price = pos.get("avg_price", 0)
            draw.text((col_avg, y), f"${avg_price:.3f}", fill=WHITE, font=font_16)

            # Current price
            current_price = pos.get("current_price", 0)
            draw.text((col_current, y), f"${current_price:.3f}", fill=WHITE, font=font_16)

            # PnL
            pnl = pos.get("pnl", 0)
            pnl_color = GREEN if pnl >= 0 else RED
            if pnl >= 0:
                pnl_text = f"+${format_with_commas(pnl, 2)}"
            else:
                pnl_text = f"-${format_with_commas(abs(pnl), 2)}"
            draw.text((col_pnl, y), pnl_text, fill=pnl_color, font=font_16)

    def save(self, path: str) -> None:
        """Save the positions card to a file."""
        img = self.generate_image()
        img.save(path)


class PnLHistoryCard:
    """
    Generate PnL history card with time-series graph.
    Shows profit/loss over a specified time period.
    """

    def __init__(
        self,
        username: str,
        pnl_data: list[dict],
        timeframe: str,
        user_icon_path: Optional[str] = None,
        background_path: Optional[str] = None,
    ):
        """
        Initialize a PnLHistoryCard.

        Args:
            username: User's display name
            pnl_data: List of PnL datapoints with keys:
                - timestamp: Unix timestamp or date string
                - pnl: Cumulative PnL at that point
            timeframe: Timeframe string - must be one of: "1D", "1W", "1M", "ALL"
            user_icon_path: Optional user profile picture path
            background_path: Optional custom background image path
        """
        # Validate timeframe
        valid_timeframes = ["1D", "1W", "1M", "ALL"]
        if timeframe not in valid_timeframes:
            raise ValueError(f"Timeframe must be one of {valid_timeframes}, got: {timeframe}")

        self.username = username
        self.pnl_data = sorted(pnl_data, key=lambda x: x.get("timestamp", 0))
        self.timeframe = timeframe
        self.user_icon_path = user_icon_path
        self.background_path = background_path

        # Calculate summary stats
        if self.pnl_data:
            self.start_pnl = self.pnl_data[0].get("pnl", 0)
            self.end_pnl = self.pnl_data[-1].get("pnl", 0)
            self.change = self.end_pnl - self.start_pnl
            self.max_pnl = max(d.get("pnl", 0) for d in self.pnl_data)
            self.min_pnl = min(d.get("pnl", 0) for d in self.pnl_data)
        else:
            self.start_pnl = 0
            self.end_pnl = 0
            self.change = 0
            self.max_pnl = 0
            self.min_pnl = 0

    @classmethod
    def new(
        cls,
        username: str,
        pnl_data: list[dict],
        timeframe: str,
    ) -> "PnLHistoryCard":
        """Create a new PnLHistoryCard."""
        return cls(
            username=username,
            pnl_data=pnl_data,
            timeframe=timeframe,
        )

    @classmethod
    def new_with_user_icon(
        cls,
        username: str,
        pnl_data: list[dict],
        timeframe: str,
        user_icon_path: str,
    ) -> "PnLHistoryCard":
        """Create a PnL history card with a custom user icon."""
        return cls(
            username=username,
            pnl_data=pnl_data,
            timeframe=timeframe,
            user_icon_path=user_icon_path,
        )

    def generate_image(self) -> Image.Image:
        """Generate the PnL history card image."""
        project_root = Path.cwd()

        # Use custom background if provided, otherwise use default from assets
        if self.background_path:
            background_to_load = self.background_path
        else:
            # Default background from assets
            background_to_load = str(project_root / "assets" / "card-background.png")

        try:
            img = Image.open(background_to_load).convert("RGBA")
            img = img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        except Exception as e:
            print(f"Failed to load background image: {e}")
            # Fallback to solid color if background not found
            img = Image.new("RGBA", (WIDTH, HEIGHT), DEFAULT_BG)

        # Load font
        project_root = Path.cwd()
        font_path = project_root / "assets" / "type_writer.ttf"

        try:
            font_path.read_bytes()
        except Exception as e:
            print(f"Failed to read font file: {e}")
            raise

        # Draw all components
        self.draw_header(img, font_path)
        self.draw_stats(img, font_path)
        self.draw_graph(img, font_path)

        return img

    def draw_header(self, img: Image.Image, font_path: Path):
        """Draw header with user info and branding."""
        draw = ImageDraw.Draw(img)
        project_root = Path.cwd()
        polymarket_path = project_root / "assets" / "polymarket-icon.png"

        icon_size = 50
        brand_x = 35
        brand_y = 30

        # Draw user icon
        if self.user_icon_path:
            user_icon = Path(self.user_icon_path)
            if not user_icon.is_absolute():
                icon_path = project_root / "assets" / self.user_icon_path
            else:
                icon_path = user_icon
        else:
            icon_path = polymarket_path

        try:
            user_img = Image.open(icon_path).convert("RGBA")
            user_resized = user_img.resize((icon_size, icon_size), Image.Resampling.LANCZOS)

            # Create circular mask
            mask = Image.new("L", (icon_size, icon_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse([0, 0, icon_size, icon_size], fill=255)

            img.paste(user_resized, (brand_x, brand_y), mask)
        except Exception:
            pass

        # Draw username
        font_28 = ImageFont.truetype(str(font_path), 28)
        text_height = 28
        text_y = brand_y + (icon_size - text_height) // 2
        draw.text(
            (brand_x + icon_size + 20, text_y),
            self.username.upper(),
            fill=WHITE,
            font=font_28
        )

        # Draw polymarket branding on right
        brand_right_x = WIDTH - 165

        try:
            polymarket_img = Image.open(polymarket_path).convert("RGBA")
            polymarket_right_size = 70  # Enlarged from 50
            polymarket_resized = polymarket_img.resize((polymarket_right_size, polymarket_right_size), Image.Resampling.LANCZOS)
            # Position much closer to OPIATE text
            polymarket_x = brand_right_x - 78  # Much closer spacing
            # Vertically align center of icon with center of username text
            text_center_y = brand_y + (icon_size // 2)
            polymarket_y = text_center_y - (polymarket_right_size // 2)
            img.paste(polymarket_resized, (polymarket_x, polymarket_y), polymarket_resized)
        except Exception:
            pass

        brand_text_y = brand_y + (icon_size - 28) // 2
        draw.text(
            (brand_right_x, brand_text_y),
            "OPIATE",
            fill=WHITE,
            font=font_28
        )

    def draw_stats(self, img: Image.Image, font_path: Path):
        """Draw summary statistics."""
        draw = ImageDraw.Draw(img)

        font_20 = ImageFont.truetype(str(font_path), 20)
        font_28 = ImageFont.truetype(str(font_path), 28)

        # Timeframe label
        draw.text((40, 100), f"PNL ({self.timeframe})", fill=GRAY, font=font_20)

        # Show only the change over the timeframe period
        change_color = GREEN if self.change >= 0 else RED
        if self.change >= 0:
            change_text = f"+${format_with_commas(self.change, 2)}"
        else:
            change_text = f"-${format_with_commas(abs(self.change), 2)}"

        draw.text((40, 130), change_text, fill=change_color, font=font_28)

    def draw_graph(self, img: Image.Image, font_path: Path):
        """Draw PnL line graph with proper axes."""
        if not self.pnl_data or len(self.pnl_data) < 2:
            # Not enough data to draw graph
            draw = ImageDraw.Draw(img)
            font_16 = ImageFont.truetype(str(font_path), 16)
            draw.text((WIDTH // 2 - 100, HEIGHT // 2), "Insufficient data for graph", fill=GRAY, font=font_16)
            return

        draw = ImageDraw.Draw(img)
        font_12 = ImageFont.truetype(str(font_path), 12)
        font_14 = ImageFont.truetype(str(font_path), 14)

        # Graph dimensions - compressed and centered
        graph_width = 540  # Further reduced
        graph_height = 180  # Compressed vertically

        # Margins for labels to prevent bleeding
        margin_left = 60  # Space for Y-axis labels
        margin_right = 15  # Space on right
        margin_bottom = 35  # Space for X-axis labels

        # Center horizontally with margins
        total_width_needed = margin_left + graph_width + margin_right
        graph_x = (WIDTH - total_width_needed) // 2 + margin_left
        graph_y = 200  # Move down slightly

        # Calculate data range
        pnl_values = [d.get("pnl", 0) for d in self.pnl_data]
        max_val = max(pnl_values)
        min_val = min(pnl_values)

        # Add padding to range
        val_range = max_val - min_val
        if val_range == 0:
            val_range = 1  # Prevent division by zero
        padding = val_range * 0.1
        max_val += padding
        min_val -= padding
        val_range = max_val - min_val

        # Draw Y-axis
        draw.line(
            [(graph_x, graph_y), (graph_x, graph_y + graph_height)],
            fill=(80, 80, 80, 255),
            width=2
        )

        # Draw X-axis
        draw.line(
            [(graph_x, graph_y + graph_height), (graph_x + graph_width, graph_y + graph_height)],
            fill=(80, 80, 80, 255),
            width=2
        )

        # Draw horizontal gridlines (5 lines)
        num_gridlines = 5
        for i in range(num_gridlines + 1):
            y = graph_y + int(i * graph_height / num_gridlines)
            # Gridline
            draw.line(
                [(graph_x, y), (graph_x + graph_width, y)],
                fill=(60, 60, 60, 100),
                width=1
            )

            # Y-axis label
            val = max_val - (i * val_range / num_gridlines)
            if abs(val) < 10:
                label = f"${val:.1f}"
            else:
                label = f"${format_with_commas(val, 0)}"

            # Right-align labels on left side
            label_width = measure_text_width(label, font_12)
            draw.text((graph_x - label_width - 8, y - 6), label, fill=GRAY, font=font_12)

        # Draw zero line if it's in range (thicker and more visible)
        if min_val <= 0 <= max_val:
            zero_y = graph_y + graph_height - int((0 - min_val) / val_range * graph_height)
            draw.line(
                [(graph_x, zero_y), (graph_x + graph_width, zero_y)],
                fill=(120, 120, 120, 200),
                width=2
            )

        # Draw X-axis labels (first, middle, last)
        import datetime
        x_label_positions = [0, len(self.pnl_data) // 2, len(self.pnl_data) - 1]
        for i in x_label_positions:
            if i < len(self.pnl_data):
                timestamp = self.pnl_data[i].get("timestamp", 0)
                date_str = datetime.datetime.fromtimestamp(timestamp).strftime("%m/%d")

                x_pos = graph_x + int(i / (len(self.pnl_data) - 1) * graph_width)
                label_width = measure_text_width(date_str, font_12)
                draw.text((x_pos - label_width // 2, graph_y + graph_height + 8), date_str, fill=GRAY, font=font_12)

        # Calculate points for line graph
        points = []
        for i, datapoint in enumerate(self.pnl_data):
            pnl = datapoint.get("pnl", 0)

            # X position (evenly spaced)
            x = graph_x + int(i / (len(self.pnl_data) - 1) * graph_width)

            # Y position (scaled to graph height)
            normalized = (pnl - min_val) / val_range
            y = graph_y + graph_height - int(normalized * graph_height)

            points.append((x, y))

        # Draw line with gradient effect (multiple lines for thickness)
        line_color = GREEN if self.end_pnl >= self.start_pnl else RED

        # Draw thicker line
        for thickness in range(3):
            offset_points = [(x, y + thickness - 1) for x, y in points]
            draw.line(offset_points, fill=line_color, width=2)

        # Draw points at each datapoint
        for x, y in points:
            draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=line_color)

    def save(self, path: str) -> None:
        """Save the PnL history card to a file."""
        img = self.generate_image()
        img.save(path)


if __name__ == "__main__":
    main()
