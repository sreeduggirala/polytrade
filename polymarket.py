# polymarket.py — thin Polymarket wrappers (Data API + CLOB; SELL uses shares)
import os
import requests
from typing import Dict, List, Tuple, Optional, Any

from dotenv import load_dotenv
from loguru import logger
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

load_dotenv()

DATA_API = "https://data-api.polymarket.com"
CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
FUNDER = os.getenv("POLYMARKET_PROXY_ADDRESS")

# signature_type:
#   0 = EOA wallet (direct private key, e.g. MetaMask export)
#   1 = Email/Magic wallet proxy
#   2 = Browser wallet proxy
# Use 1 when POLYMARKET_PROXY_ADDRESS is a Polymarket-generated proxy wallet
SIGNATURE_TYPE = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "1"))

if not PRIVATE_KEY:
    raise RuntimeError("Set PRIVATE_KEY in .env")
if not FUNDER:
    raise RuntimeError("Set POLYMARKET_PROXY_ADDRESS in .env (your funder/proxy address)")

_client: Optional[ClobClient] = None


def clob() -> ClobClient:
    """Get or create the singleton ClobClient instance."""
    global _client
    if _client is None:
        logger.info(f"Initializing ClobClient: host={CLOB_HOST}, chain_id={CHAIN_ID}, signature_type={SIGNATURE_TYPE}")
        c = ClobClient(
            host=CLOB_HOST,
            key=PRIVATE_KEY,
            chain_id=CHAIN_ID,
            signature_type=SIGNATURE_TYPE,
            funder=FUNDER,
        )
        creds = c.create_or_derive_api_creds()
        c.set_api_creds(creds)
        _client = c
        logger.info("ClobClient initialized successfully")
    return _client

# ---------- Data API (for tracking other wallets) ----------
def fetch_trades_for_user(user: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Fetch recent trades for a user from the Polymarket Data API.
    Returns newest trades first.
    """
    try:
        r = requests.get(
            f"{DATA_API}/trades",
            params={"user": user.lower(), "limit": limit},
            timeout=15
        )
        r.raise_for_status()
        data = r.json()

        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "data" in data:
            # Some API versions wrap in {"data": [...]}
            return data["data"] if isinstance(data["data"], list) else []
        else:
            logger.warning(f"Unexpected response format from Data API: {type(data)}")
            return []

    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching trades for {user}")
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching trades for {user}: {e}")
        return []
    except Exception as e:
        logger.exception(f"Unexpected error fetching trades for {user}: {e}")
        return []


def trade_ptr(t: Dict[str, Any]) -> Tuple[int, str, int]:
    """Extract a unique cursor (timestamp, tx_hash, log_index) from a trade."""
    ts = int(t.get("timestamp") or 0)
    tx = str(t.get("tx_hash") or "")
    li = int(t.get("log_index") or 0)
    return (ts, tx, li)

# ---------- Quotes ----------
def best_quotes(token_id: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Return (best_bid_price, best_ask_price) as floats, or (None, None) if unavailable.
    """
    try:
        ob = clob().get_order_book(token_id)
        if not ob:
            logger.warning(f"No order book returned for token {token_id}")
            return None, None

        best_bid = float(ob.bids[0].price) if ob.bids else None
        best_ask = float(ob.asks[0].price) if ob.asks else None
        return best_bid, best_ask

    except Exception as e:
        logger.error(f"Error fetching order book for {token_id}: {e}")
        return None, None


# ---------- Market order helpers ----------
def _parse_order_response(resp: Any) -> bool:
    """
    Parse the response from post_order. The response format can vary.
    Returns True if order was successful.
    """
    if resp is None:
        return False

    # Response could be a dict with various success indicators
    if isinstance(resp, dict):
        # Check common success fields
        if resp.get("success"):
            return True
        if resp.get("orderID") or resp.get("order_id"):
            return True
        if resp.get("status") == "matched" or resp.get("status") == "filled":
            return True
        # FOK orders that don't fill return specific status
        if resp.get("status") == "cancelled":
            logger.warning(f"Order cancelled (likely FOK not filled): {resp}")
            return False

    # If we got here with a non-empty response, log it for debugging
    logger.debug(f"Order response: {resp}")
    return bool(resp)


def market_buy_notional(token_id: str, notional_usdc: float) -> bool:
    """
    Place a market BUY order.
    Per Polymarket docs: BUY amount is in USDC (dollars).
    """
    if notional_usdc <= 0:
        logger.warning(f"Invalid notional for BUY: {notional_usdc}")
        return False

    try:
        logger.info(f"Placing market BUY: token={token_id}, notional=${notional_usdc:.2f}")
        args = MarketOrderArgs(
            token_id=str(token_id),
            amount=float(notional_usdc),
            side=BUY
        )
        order = clob().create_market_order(args)
        resp = clob().post_order(order, OrderType.FOK)

        success = _parse_order_response(resp)
        if success:
            logger.info(f"BUY order successful: {resp}")
        else:
            logger.warning(f"BUY order may have failed: {resp}")
        return success

    except Exception as e:
        logger.exception(f"Exception placing BUY order: {e}")
        return False


def market_sell_notional(token_id: str, notional_usdc: float) -> bool:
    """
    Place a market SELL order.
    Per Polymarket docs: SELL amount is in SHARES (not USDC).
    We convert desired USDC notional into shares using the current best bid price.
    """
    if notional_usdc <= 0:
        logger.warning(f"Invalid notional for SELL: {notional_usdc}")
        return False

    try:
        best_bid, _ = best_quotes(token_id)
        if not best_bid or best_bid <= 0:
            logger.warning(f"No valid bid price for SELL on token {token_id}")
            return False

        # Convert USDC notional to shares: shares = notional / price
        shares = float(notional_usdc) / float(best_bid)
        if shares <= 0:
            logger.warning(f"Calculated shares <= 0: {shares}")
            return False

        logger.info(f"Placing market SELL: token={token_id}, shares={shares:.4f} (from ${notional_usdc:.2f} @ bid {best_bid:.4f})")
        args = MarketOrderArgs(
            token_id=str(token_id),
            amount=shares,
            side=SELL
        )
        order = clob().create_market_order(args)
        resp = clob().post_order(order, OrderType.FOK)

        success = _parse_order_response(resp)
        if success:
            logger.info(f"SELL order successful: {resp}")
        else:
            logger.warning(f"SELL order may have failed: {resp}")
        return success

    except Exception as e:
        logger.exception(f"Exception placing SELL order: {e}")
        return False
