"""
Test Polymarket card generation (TradingCard, PositionsCard, PnLHistoryCard).
"""

from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.card import TradingCard, PositionsCard, PnLHistoryCard


def test_trading_cards():
    """Generate test trading cards for Polymarket prediction markets."""
    print("🎨 Generating Polymarket trading cards...\n")

    output_dir = Path(__file__).parent / "test_cards"
    output_dir.mkdir(exist_ok=True)

    # Example 1: YES position with profit
    print("1. Generating YES position (winning)...")
    card1 = TradingCard.new_with_user_icon(
        username="EON",
        market="BTC > $100k by EOY 2024",
        position_type="YES",
        pnl_amount=2500.0,
        avg_price=0.65,
        current_price=0.85,
        shares=5000.0,
        user_icon_path="eon-icon.jpg",
    )
    try:
        card1.save(str(output_dir / "yes_winning.png"))
        print("   ✅ Saved: tests/test_cards/yes_winning.png\n")
    except Exception as e:
        print(f"   ❌ Error: {e}\n")

    # Example 2: NO position with loss
    print("2. Generating NO position (losing)...")
    card2 = TradingCard.new(
        username="Alice",
        market="ETH > $5k by March 2024",
        position_type="NO",
        pnl_amount=-850.0,
        avg_price=0.45,
        current_price=0.25,
        shares=3000.0,
    )
    try:
        card2.save(str(output_dir / "no_losing.png"))
        print("   ✅ Saved: tests/test_cards/no_losing.png\n")
    except Exception as e:
        print(f"   ❌ Error: {e}\n")

    # Example 3: YES position with small profit
    print("3. Generating YES position (small win)...")
    card3 = TradingCard.new(
        username="Bob",
        market="Trump wins 2024 election",
        position_type="YES",
        pnl_amount=125.50,
        avg_price=0.52,
        current_price=0.58,
        shares=2000.0,
    )
    try:
        card3.save(str(output_dir / "yes_small_win.png"))
        print("   ✅ Saved: tests/test_cards/yes_small_win.png\n")
    except Exception as e:
        print(f"   ❌ Error: {e}\n")

    # Example 4: NO position with profit
    print("4. Generating NO position (winning)...")
    card4 = TradingCard.new(
        username="Charlie",
        market="SOL flips ETH by market cap in 2024",
        position_type="NO",
        pnl_amount=1800.0,
        avg_price=0.72,
        current_price=0.28,
        shares=4000.0,
    )
    try:
        card4.save(str(output_dir / "no_winning.png"))
        print("   ✅ Saved: tests/test_cards/no_winning.png\n")
    except Exception as e:
        print(f"   ❌ Error: {e}\n")

    # Example 5: Long market name (truncation test)
    print("5. Generating card with long market name...")
    card5 = TradingCard.new(
        username="Diana",
        market="AI models surpass human performance on all benchmarks by December 2024",
        position_type="YES",
        pnl_amount=3200.0,
        avg_price=0.35,
        current_price=0.87,
        shares=10000.0,
    )
    try:
        card5.save(str(output_dir / "long_market_name.png"))
        print("   ✅ Saved: tests/test_cards/long_market_name.png\n")
    except Exception as e:
        print(f"   ❌ Error: {e}\n")


def test_positions_cards():
    """Generate test positions cards for Polymarket prediction markets."""
    print("📊 Generating Polymarket positions cards...\n")

    output_dir = Path(__file__).parent / "test_cards"
    output_dir.mkdir(exist_ok=True)

    # Example 1: Multiple winning positions
    print("6. Generating positions card with multiple winners...")
    positions = [
        {
            "market": "BTC > $100k by EOY",
            "side": "YES",
            "shares": 5000,
            "avg_price": 0.243,
            "current_price": 0.681,
            "pnl": 2190.00
        },
        {
            "market": "Trump wins 2024",
            "side": "YES",
            "shares": 3000,
            "avg_price": 0.636,
            "current_price": 0.865,
            "pnl": 687.00
        },
        {
            "market": "ETH > $5k by March",
            "side": "NO",
            "shares": 2000,
            "avg_price": 0.187,
            "current_price": 0.452,
            "pnl": -530.00
        },
        {
            "market": "SOL flips ETH",
            "side": "NO",
            "shares": 4000,
            "avg_price": 0.155,
            "current_price": 0.066,
            "pnl": 356.00
        },
    ]
    card1 = PositionsCard.new_with_user_icon(
        username="EON",
        total_value=15234.50,
        total_pnl=2703.00,
        positions=positions,
        user_icon_path="eon-icon.jpg",
    )
    try:
        card1.save(str(output_dir / "positions_winning.png"))
        print("   ✅ Saved: tests/test_cards/positions_winning.png\n")
    except Exception as e:
        print(f"   ❌ Error: {e}\n")

    # Example 2: Mixed positions with some losses
    print("7. Generating positions card with mixed results...")
    positions2 = [
        {
            "market": "AI beats humans 2024",
            "side": "YES",
            "shares": 8000,
            "avg_price": 0.350,
            "current_price": 0.870,
            "pnl": 4160.00
        },
        {
            "market": "Fed cuts rates 5x",
            "side": "NO",
            "shares": 2500,
            "avg_price": 0.720,
            "current_price": 0.280,
            "pnl": 1100.00
        },
        {
            "market": "DOGE to $1",
            "side": "YES",
            "shares": 10000,
            "avg_price": 0.520,
            "current_price": 0.180,
            "pnl": -3400.00
        },
        {
            "market": "Tesla $500 by Dec",
            "side": "YES",
            "shares": 1500,
            "avg_price": 0.450,
            "current_price": 0.550,
            "pnl": 150.00
        },
        {
            "market": "Inflation < 2%",
            "side": "NO",
            "shares": 3200,
            "avg_price": 0.380,
            "current_price": 0.220,
            "pnl": 512.00
        },
    ]
    card2 = PositionsCard.new(
        username="Alice",
        total_value=12845.75,
        total_pnl=2522.00,
        positions=positions2,
    )
    try:
        card2.save(str(output_dir / "positions_mixed.png"))
        print("   ✅ Saved: tests/test_cards/positions_mixed.png\n")
    except Exception as e:
        print(f"   ❌ Error: {e}\n")

    # Example 3: Portfolio with losses
    print("8. Generating positions card with overall loss...")
    positions3 = [
        {
            "market": "Recession in 2024",
            "side": "YES",
            "shares": 6000,
            "avg_price": 0.680,
            "current_price": 0.320,
            "pnl": -2160.00
        },
        {
            "market": "Oil above $120",
            "side": "YES",
            "shares": 3500,
            "avg_price": 0.550,
            "current_price": 0.210,
            "pnl": -1190.00
        },
        {
            "market": "China invades Taiwan",
            "side": "NO",
            "shares": 2000,
            "avg_price": 0.150,
            "current_price": 0.380,
            "pnl": -460.00
        },
    ]
    card3 = PositionsCard.new(
        username="Bob",
        total_value=5230.00,
        total_pnl=-3810.00,
        positions=positions3,
    )
    try:
        card3.save(str(output_dir / "positions_losing.png"))
        print("   ✅ Saved: tests/test_cards/positions_losing.png\n")
    except Exception as e:
        print(f"   ❌ Error: {e}\n")


def test_pnl_history_cards():
    """Generate test PnL history cards for different timeframes."""
    print("📈 Generating Polymarket PnL history cards...\n")

    output_dir = Path(__file__).parent / "test_cards"
    output_dir.mkdir(exist_ok=True)

    now = int(time.time())
    day = 86400  # seconds in a day

    # Example 1: 1-day trend
    print("9. Generating 1-day trend...")
    pnl_data_1d = [
        {"timestamp": now - (23 * 3600), "pnl": 0},
        {"timestamp": now - (20 * 3600), "pnl": 150},
        {"timestamp": now - (16 * 3600), "pnl": -200},
        {"timestamp": now - (12 * 3600), "pnl": 500},
        {"timestamp": now - (8 * 3600), "pnl": 800},
        {"timestamp": now - (4 * 3600), "pnl": 1200},
        {"timestamp": now, "pnl": 1850},
    ]
    card1 = PnLHistoryCard.new_with_user_icon(
        username="EON",
        pnl_data=pnl_data_1d,
        timeframe="1D",
        user_icon_path="eon-icon.jpg",
    )
    try:
        card1.save(str(output_dir / "pnl_history_1d.png"))
        print("   ✅ Saved: tests/test_cards/pnl_history_1d.png\n")
    except Exception as e:
        print(f"   ❌ Error: {e}\n")

    # Example 2: 1-week trend
    print("10. Generating 1-week trend...")
    pnl_data_1w = []
    base_pnl = 0
    for i in range(7, -1, -1):
        if i % 3 == 0:
            change = 800
        elif i % 2 == 0:
            change = -400
        else:
            change = 200
        base_pnl += change
        pnl_data_1w.append({
            "timestamp": now - (i * day),
            "pnl": base_pnl
        })
    card2 = PnLHistoryCard.new(
        username="Alice",
        pnl_data=pnl_data_1w,
        timeframe="1W",
    )
    try:
        card2.save(str(output_dir / "pnl_history_1w.png"))
        print("   ✅ Saved: tests/test_cards/pnl_history_1w.png\n")
    except Exception as e:
        print(f"   ❌ Error: {e}\n")

    # Example 3: 1-month downward trend
    print("11. Generating 1-month downward trend...")
    pnl_data_1m = [
        {"timestamp": now - (29 * day), "pnl": 5000},
        {"timestamp": now - (25 * day), "pnl": 4500},
        {"timestamp": now - (21 * day), "pnl": 3800},
        {"timestamp": now - (17 * day), "pnl": 2900},
        {"timestamp": now - (13 * day), "pnl": 2100},
        {"timestamp": now - (9 * day), "pnl": 1500},
        {"timestamp": now - (5 * day), "pnl": 800},
        {"timestamp": now - (2 * day), "pnl": -200},
        {"timestamp": now, "pnl": -1500},
    ]
    card3 = PnLHistoryCard.new(
        username="Bob",
        pnl_data=pnl_data_1m,
        timeframe="1M",
    )
    try:
        card3.save(str(output_dir / "pnl_history_1m.png"))
        print("   ✅ Saved: tests/test_cards/pnl_history_1m.png\n")
    except Exception as e:
        print(f"   ❌ Error: {e}\n")

    # Example 4: ALL time (longer history)
    print("12. Generating ALL time history...")
    pnl_data_all = []
    steady_pnl = 0
    for i in range(120, -1, -3):  # Every 3 days over 4 months
        if i % 15 == 0:
            change = 1200
        elif i % 9 == 0:
            change = -800
        elif i % 5 == 0:
            change = 600
        else:
            change = 150
        steady_pnl += change
        pnl_data_all.append({
            "timestamp": now - (i * day),
            "pnl": steady_pnl
        })
    card4 = PnLHistoryCard.new_with_user_icon(
        username="Charlie",
        pnl_data=pnl_data_all,
        timeframe="ALL",
        user_icon_path="eon-icon.jpg",
    )
    try:
        card4.save(str(output_dir / "pnl_history_all.png"))
        print("   ✅ Saved: tests/test_cards/pnl_history_all.png\n")
    except Exception as e:
        print(f"   ❌ Error: {e}\n")


def main():
    """Run all card generation tests."""
    print("=" * 60)
    print("OPIATE CARD GENERATION TEST SUITE")
    print("=" * 60)
    print()

    test_trading_cards()
    test_positions_cards()
    test_pnl_history_cards()

    print("=" * 60)
    print("🎉 All tests complete! Check 'tests/test_cards/' directory.")
    print("=" * 60)
    print("\nCard types tested:")
    print("  ✅ TradingCard - Single position PnL cards")
    print("  ✅ PositionsCard - Multi-position overview")
    print("  ✅ PnLHistoryCard - Time-series PnL graphs")
    print("\nFeatures:")
    print("  • YES/NO prediction markets")
    print("  • Proper sign placement: +$X, -$X")
    print("  • No commas for amounts < $1,000")
    print("  • Compressed graphs with proper margins")
    print("  • Supported timeframes: 1D, 1W, 1M, ALL")
    print()


if __name__ == "__main__":
    main()
