# main.py — copytrader loop: 1) get new trades, 2) mirror, 3) announce
import os
import json
import time
import asyncio
from typing import Dict, Tuple, Optional
from dotenv import load_dotenv
from loguru import logger

from polymarket import (
    fetch_trades_for_user,
    trade_ptr,
    market_buy_notional,
    market_sell_notional,
)
from utils.telegram import send_markdown, close_session

load_dotenv()

# --- config ---
TRADE_SCALE = float(os.getenv("TRADE_SCALE", "1.0"))   # 1.0=same notional as source
POLL_SEC = float(os.getenv("POLL_SEC", "2.0"))

TARGETS: Dict[str,str] = {  # wallet -> name
    "0xd218e474776403a330142299f7796e8ba32eb5c9": "cigarettes",
    # add more …
}

CURSORS_FILE = os.getenv("CURSORS_FILE", "last_seen.json")

# Cursor is (timestamp, tx_hash, log_index) - we use timestamp as primary ordering
def load_cursors() -> Dict[str, Tuple[int, str, int]]:
    """Load cursor state from disk. Returns empty dict on error."""
    try:
        with open(CURSORS_FILE, "r") as f:
            data = json.load(f)
        return {w: tuple(v) for w, v in data.items()}
    except FileNotFoundError:
        logger.info(f"No cursor file found at {CURSORS_FILE}, starting fresh")
        return {}
    except Exception as e:
        logger.warning(f"Failed to load cursors: {e}")
        return {}

def save_cursors(c: Dict[str, Tuple[int, str, int]]) -> None:
    """Persist cursor state to disk."""
    try:
        with open(CURSORS_FILE, "w") as f:
            json.dump({w: list(v) for w, v in c.items()}, f)
    except Exception as e:
        logger.error(f"Failed to save cursors: {e}")

def cursor_is_newer(cur: Tuple[int, str, int], last: Tuple[int, str, int]) -> bool:
    """
    Compare two trade cursors. Returns True if cur is strictly newer than last.
    Uses timestamp as primary key, then (tx_hash, log_index) for same-second disambiguation.
    """
    cur_ts, cur_tx, cur_li = cur
    last_ts, last_tx, last_li = last

    if cur_ts != last_ts:
        return cur_ts > last_ts
    # Same timestamp: compare tx_hash and log_index
    if cur_tx != last_tx:
        return cur_tx > last_tx  # lexicographic, not perfect but consistent
    return cur_li > last_li

def format_announce(t: dict, name: str, ok: bool, error: Optional[str] = None) -> str:
    """Format a trade notification message for Telegram."""
    side = "BUY" if t.get("is_buy") else "SELL"
    title = t.get("title") or t.get("question") or "Unknown market"
    price = float(t.get("price") or 0.0)
    amt = float(t.get("amount") or 0.0)
    notional = amt * price * TRADE_SCALE
    when = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(t.get("timestamp") or 0)))

    if ok:
        status = "✅ mirrored"
    else:
        status = f"❌ mirror failed: {error}" if error else "❌ mirror failed"

    return (
        f"*{name}* — *{side}* {amt:.2f} shares @ {price:.3f}\n"
        f"Mirrored: ${notional:.2f}\n"
        f"{title}\n"
        f"`token_id:` `{t.get('token_id', '')}`\n"
        f"`tx:` `{t.get('tx_hash', '')}`\n"
        f"{when}\n\n"
        f"{status}"
    )

def mirror_trade(t: dict) -> Tuple[bool, Optional[str]]:
    """
    Mirror a trade from the tracked wallet.
    Returns (success, error_message).

    Note: Polymarket Data API 'amount' is in shares, not USDC notional.
    We calculate notional as: shares * price.
    """
    try:
        shares = float(t.get("amount") or 0.0)
        price = float(t.get("price") or 0.0)
        token_id = t.get("token_id")

        if not token_id:
            return False, "Missing token_id"
        if shares <= 0:
            return False, f"Invalid shares amount: {shares}"
        if price <= 0:
            return False, f"Invalid price: {price}"

        # Calculate notional value (USDC) from shares * price
        notional = shares * price * TRADE_SCALE

        if notional <= 0:
            return False, f"Notional too small after scaling: {notional}"

        is_buy = t.get("is_buy")
        side_str = "BUY" if is_buy else "SELL"
        logger.info(f"Mirroring {side_str}: {shares:.4f} shares @ {price:.4f} = ${notional:.2f} (scaled)")

        if is_buy:
            success = market_buy_notional(token_id, notional)
        else:
            success = market_sell_notional(token_id, notional)

        if success:
            return True, None
        else:
            return False, "Order execution failed"

    except Exception as e:
        logger.exception(f"Exception in mirror_trade: {e}")
        return False, str(e)

async def async_main():
    """Main copytrading loop with proper async handling."""
    cursors = load_cursors()
    logger.info(f"Starting copytrader: TRADE_SCALE={TRADE_SCALE}, polling={POLL_SEC}s, wallets={len(TARGETS)}")

    last_heartbeat = 0

    while True:
        sweep_start = time.time()

        for wallet, name in TARGETS.items():
            try:
                last_seen = cursors.get(wallet, (0, "", 0))
                items = fetch_trades_for_user(wallet, limit=50)  # Returns newest first

                if not items:
                    continue

                newest = trade_ptr(items[0])
                logger.debug(f"[{name}] fetched {len(items)} trades, newest={newest}, last_seen={last_seen}")

                # CRITICAL: Reverse to process oldest->newest
                # This ensures if we fail mid-way, we retry from where we stopped
                new_trades = []
                for t in items:
                    cur = trade_ptr(t)
                    if cursor_is_newer(cur, last_seen):
                        new_trades.append(t)

                # Process oldest first so cursor advances correctly
                new_trades.reverse()

                for t in new_trades:
                    cur = trade_ptr(t)
                    ok, error = mirror_trade(t)
                    msg = format_announce(t, name, ok, error)

                    try:
                        await send_markdown(msg)
                    except Exception as e:
                        logger.error(f"Failed to send Telegram notification: {e}")

                    if ok:
                        # Only advance cursor on successful mirror
                        cursors[wallet] = cur
                        save_cursors(cursors)  # Save immediately after each success
                        logger.info(f"[{name}] Successfully mirrored trade, cursor updated to {cur}")
                    else:
                        logger.warning(f"[{name}] Mirror failed for trade {cur}: {error}")
                        # Don't update cursor - we'll retry this trade next poll

            except Exception as e:
                logger.exception(f"[{name}] Error processing wallet: {e}")

        # Heartbeat every ~10 mins
        current_time = time.time()
        if current_time - last_heartbeat >= 600:
            try:
                await send_markdown("_heartbeat: copytrader alive_")
                last_heartbeat = current_time
            except Exception as e:
                logger.error(f"Failed to send heartbeat: {e}")

        # Maintain polling cadence
        elapsed = time.time() - sweep_start
        sleep_time = max(0.1, POLL_SEC - elapsed)
        await asyncio.sleep(sleep_time)


async def shutdown():
    """Cleanup resources on shutdown."""
    logger.info("Shutting down...")
    await close_session()
    logger.info("Cleanup complete")


def main():
    """Entry point - runs the async main loop with proper cleanup."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(async_main())
    except KeyboardInterrupt:
        logger.info("Copytrader stopped by user")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        raise
    finally:
        # Cleanup
        loop.run_until_complete(shutdown())
        loop.close()


if __name__ == "__main__":
    main()
