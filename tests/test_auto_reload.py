"""
Test script for BNB auto-reload functionality using deBridge DLN
"""

import os
import asyncio
import pytest
from dotenv import load_dotenv
from utils.account import AccountManager
from utils.auto_reload import BNBReloader, check_and_reload_bnb

load_dotenv()


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPINION_PRIVATE_KEY"), reason="OPINION_PRIVATE_KEY not set")
async def test_reload_status():
    """Test reload status checking."""
    print("\n" + "=" * 60)
    print("BNB AUTO-RELOAD TEST (Using deBridge)")
    print("=" * 60)

    # Load account
    private_key = os.getenv("OPINION_PRIVATE_KEY")
    if not private_key:
        print("❌ OPINION_PRIVATE_KEY not found in environment")
        return

    print("\n1. Loading account...")
    account_mgr = AccountManager(private_key=private_key, testnet=False)
    print(f"   Address: {account_mgr.get_address()}")

    print("\n2. Checking current balances...")
    balances = account_mgr.get_all_balances()
    print(f"   BNB: {balances['bnb']:.6f}")
    print(f"   USDT: ${balances['usdt']:.2f}")

    print("\n3. Initializing BNB Reloader (with deBridge)...")
    reloader = BNBReloader(
        account_manager=account_mgr,
        threshold=0.01,  # 0.01 BNB threshold
        reload_amount=0.02  # Reload to 0.02 BNB
    )

    print("\n4. Checking reload status...")
    status = reloader.get_current_status()

    print(f"\n   Current Status:")
    print(f"   • BNB Balance: {status['bnb_balance']:.6f}")
    print(f"   • USDT Balance: ${status['usdt_balance']:.2f}")
    print(f"   • Threshold: {status['threshold']:.6f} BNB")
    print(f"   • Reload Amount: {status['reload_amount']:.6f} BNB")
    print(f"   • Needs Reload: {'⚠️ YES' if status['needs_reload'] else '✅ NO'}")

    if status['needs_reload']:
        print(f"\n   Reload Details:")
        print(f"   • BNB Needed: {status['bnb_needed']:.6f}")
        print(f"   • Est. USDT Cost: ${status['usdt_needed']:.2f}")
        print(f"   • Has Sufficient USDT: {'✅ YES' if status['has_sufficient_usdt'] else '❌ NO'}")

    print("\n5. Testing USDT -> BNB price estimation via deBridge...")
    try:
        # Estimate how much BNB we'd get for 10 USDT
        bnb_for_10_usdt = await reloader.estimate_bnb_for_usdt(10.0)
        print(f"   10 USDT ≈ {bnb_for_10_usdt:.6f} BNB")

        if bnb_for_10_usdt > 0:
            bnb_price = 10.0 / bnb_for_10_usdt
            print(f"   Current BNB price: ~${bnb_price:.2f}")
    except Exception as e:
        print(f"   ⚠️ Price estimation error: {e}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

    print("\n💡 HOW IT WORKS:")
    print("   deBridge DLN provides decentralized liquidity:")
    print("   • Cross-chain and same-chain swaps")
    print("   • No centralized relayers")
    print("   • Competitive pricing")
    print("\n   deBridge handles USDT -> BNB swaps on BSC!")

    # Ask if user wants to test actual reload (for safety)
    if status['needs_reload'] and status['has_sufficient_usdt']:
        print("\n⚠️  BNB reload is needed and USDT is available.")
        print("    To test actual reload, run:")
        print('    python -c "import asyncio; from test_bnb_reload import test_actual_reload; asyncio.run(test_actual_reload())"')
    elif status['needs_reload']:
        print("\n⚠️  BNB reload is needed but insufficient USDT.")
        print("    Please deposit more USDT to test the reload feature.")
    else:
        print("\n✅ BNB balance is sufficient. No reload needed.")


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPINION_PRIVATE_KEY"), reason="OPINION_PRIVATE_KEY not set")
@pytest.mark.skip(reason="Requires real blockchain transaction - run manually if needed")
async def test_actual_reload():
    """
    Test actual BNB reload using deBridge (WARNING: This will execute a real transaction!)
    Only run this if you understand the implications.
    """
    print("\n" + "=" * 60)
    print("⚠️  ACTUAL BNB RELOAD TEST (REAL TRANSACTION via deBridge)")
    print("=" * 60)

    confirmation = input("\nType 'YES' to proceed with real reload: ")
    if confirmation != "YES":
        print("Aborted.")
        return

    private_key = os.getenv("OPINION_PRIVATE_KEY")
    if not private_key:
        print("❌ OPINION_PRIVATE_KEY not found")
        return

    print("\nInitializing reload with deBridge...")
    account_mgr = AccountManager(private_key=private_key, testnet=False)

    result = await check_and_reload_bnb(
        account_manager=account_mgr,
        threshold=0.01,
        reload_amount=0.02
    )

    if result:
        if result.get("success"):
            print("\n✅ RELOAD SUCCESSFUL!")
            print(f"   Protocol Used: {result.get('route_protocol', 'deBridge')}")
            print(f"   USDT Spent: ${result['usdt_spent']:.2f}")
            print(f"   BNB Received: {result['bnb_received']:.6f}")
            print(f"   New BNB Balance: {result['new_bnb_balance']:.6f}")
            print(f"   Order ID: {result.get('order_id', 'N/A')}")
            print(f"   Swap Tx: {result['swap_tx']}")
            print(f"\n   deBridge DLN completed the swap!")
        else:
            print(f"\n❌ RELOAD FAILED: {result.get('error')}")
    else:
        print("\n✅ No reload needed - balance is sufficient")


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPINION_PRIVATE_KEY"), reason="OPINION_PRIVATE_KEY not set")
async def test_debridge_quote():
    """Test getting a quote from deBridge for USDT -> BNB swap."""
    print("\n" + "=" * 60)
    print("TESTING DEBRIDGE QUOTE FOR USDT -> BNB")
    print("=" * 60)

    private_key = os.getenv("OPINION_PRIVATE_KEY")
    if not private_key:
        print("❌ OPINION_PRIVATE_KEY not found")
        return

    account_mgr = AccountManager(private_key=private_key, testnet=False)

    print(f"\nUser Address: {account_mgr.get_address()}")

    print("\nGetting quote for 10 USDT -> BNB swap on BSC...")

    from utils.debridge import DeBridgeClient, ChainId
    from utils.account import to_wei

    async with DeBridgeClient() as debridge:
        # 10 USDT in wei (18 decimals)
        usdt_amount = to_wei(10, 18)

        quote = await debridge.get_quote(
            src_chain_id=ChainId.BSC.value,
            src_token="0x55d398326f99059fF775485246999027B3197955",  # USDT on BSC
            dst_chain_id=ChainId.BSC.value,
            dst_token="0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",  # Native BNB
            src_amount=str(usdt_amount),
            src_address=account_mgr.get_address(),
        )

        from_amount = float(quote.give_amount) / 10**18
        to_amount = float(quote.take_amount) / 10**18

        print(f"\n✅ deBridge Quote:\n")
        print(f"  Input: {from_amount:.2f} USDT")
        print(f"  Output: {to_amount:.6f} BNB")
        print(f"  Fixed Fee: {quote.fixed_fee}")
        print(f"  Percent Fee: {quote.percent_fee}")

        if to_amount > 0:
            price = from_amount / to_amount
            print(f"  BNB Price: ${price:.2f}")
        print()


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPINION_PRIVATE_KEY"), reason="OPINION_PRIVATE_KEY not set")
async def test_convenience_function():
    """Test the convenience function."""
    print("\n" + "=" * 60)
    print("TESTING CONVENIENCE FUNCTION")
    print("=" * 60)

    private_key = os.getenv("OPINION_PRIVATE_KEY")
    if not private_key:
        print("❌ OPINION_PRIVATE_KEY not found")
        return

    print("\nChecking if reload is needed...")
    account_mgr = AccountManager(private_key=private_key, testnet=False)

    result = await check_and_reload_bnb(
        account_manager=account_mgr,
        threshold=0.01,
        reload_amount=0.02
    )

    if result is None:
        print("✅ No reload needed - balance is sufficient")
    elif result.get("success"):
        print(f"✅ Reload successful via {result.get('route_protocol')}!")
        print(f"   New balance: {result['new_bnb_balance']:.6f} BNB")
    else:
        print(f"❌ Reload failed: {result.get('error')}")


if __name__ == "__main__":
    # Run status check by default (safe)
    asyncio.run(test_reload_status())
