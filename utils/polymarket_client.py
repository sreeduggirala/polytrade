"""
Polymarket Prediction Market API Client

Complete implementation matching PolymarketClient interface for easy migration.
Supports per-user instantiation for multi-user Telegram bot.

API Documentation:
- https://docs.polymarket.com
- https://github.com/Polymarket/py-clob-client
"""

from enum import IntEnum
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
import os
import time
import requests

from loguru import logger
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs, OrderType as ClobOrderType
from py_clob_client.order_builder.constants import BUY, SELL


# ============================================================================
# CONSTANTS
# ============================================================================

DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet

USDC_DECIMALS = 6


# ============================================================================
# GLOBAL CACHE (Shared across all PolymarketClient instances)
# ============================================================================

_GLOBAL_MARKETS_CACHE: Optional[List['Market']] = None
_GLOBAL_MARKETS_CACHE_TIME: float = 0
_CACHE_TTL: int = 300  # 5 minutes


# ============================================================================
# ENUMS (Match Polymarket's interface)
# ============================================================================

class TopicType(IntEnum):
    """Market classification types."""
    BINARY = 0
    CATEGORICAL = 1


class TopicStatus(IntEnum):
    """Market lifecycle stages."""
    CREATED = 1
    ACTIVATED = 2
    RESOLVING = 3
    RESOLVED = 4


class TopicStatusFilter:
    """Query filter for market status."""
    ALL = "all"
    ACTIVATED = "activated"
    RESOLVED = "resolved"


class OrderSide(IntEnum):
    """Trade direction."""
    BUY = 0
    SELL = 1


class OrderType(IntEnum):
    """Order execution methods."""
    MARKET_ORDER = 1
    LIMIT_ORDER = 2


# ============================================================================
# EXCEPTIONS
# ============================================================================

class PolymarketError(Exception):
    """Base exception for Polymarket errors."""
    pass


class OpenApiError(PolymarketError):
    """API returned an error."""
    pass


class BalanceNotEnough(PolymarketError):
    """Insufficient balance for operation."""
    pass


class InvalidParamError(PolymarketError):
    """Invalid parameters."""
    pass


# ============================================================================
# DATA CLASSES (Match Polymarket's interface)
# ============================================================================

@dataclass
class PlaceOrderDataInput:
    """Order submission parameters (Polymarket-compatible)."""
    marketId: str  # condition_id for Polymarket
    tokenId: str
    side: int  # OrderSide.BUY or OrderSide.SELL
    orderType: int  # OrderType.MARKET_ORDER or OrderType.LIMIT_ORDER
    price: str  # Price string; "0" for market orders
    makerAmountInQuoteToken: Optional[str] = None  # USDC amount
    makerAmountInBaseToken: Optional[str] = None  # Share quantity

    def validate(self):
        """Validate that exactly one amount field is provided."""
        has_quote = self.makerAmountInQuoteToken is not None
        has_base = self.makerAmountInBaseToken is not None
        if not (has_quote ^ has_base):
            raise InvalidParamError(
                "Must provide exactly one of makerAmountInQuoteToken or makerAmountInBaseToken"
            )


@dataclass
class Market:
    """Market data structure (Polymarket-compatible)."""
    marketId: str  # condition_id
    marketTitle: str
    status: int
    marketType: int  # 0=BINARY, 1=CATEGORICAL
    conditionId: str
    quoteToken: str
    chainId: int
    volume: float
    cutoffAt: Optional[int] = None
    resolvedAt: Optional[int] = None
    rules: Optional[str] = None
    tokenIds: List[str] = field(default_factory=list)
    # Binary market fields
    yesTokenId: Optional[str] = None
    noTokenId: Optional[str] = None
    yesLabel: Optional[str] = None
    noLabel: Optional[str] = None
    resultTokenId: Optional[str] = None
    # Categorical market fields
    options: Optional[List[Dict[str, Any]]] = None
    # Extra Polymarket fields
    slug: Optional[str] = None
    image: Optional[str] = None

    @classmethod
    def from_gamma_api(cls, data: Dict[str, Any]) -> "Market":
        """Create Market from Gamma API response."""
        tokens = data.get("tokens", [])
        token_ids = [t.get("token_id", "") for t in tokens]

        # Determine market type
        is_binary = len(tokens) == 2

        # Extract YES/NO tokens for binary markets
        yes_token_id = None
        no_token_id = None
        if is_binary:
            for t in tokens:
                outcome = t.get("outcome", "").upper()
                if outcome == "YES":
                    yes_token_id = t.get("token_id")
                elif outcome == "NO":
                    no_token_id = t.get("token_id")

        # Build options for categorical
        options = None
        if not is_binary and tokens:
            options = [
                {"tokenId": t.get("token_id"), "label": t.get("outcome")}
                for t in tokens
            ]

        return cls(
            marketId=data.get("condition_id", ""),
            marketTitle=data.get("question", ""),
            status=TopicStatus.ACTIVATED if data.get("active") else TopicStatus.RESOLVED,
            marketType=TopicType.BINARY if is_binary else TopicType.CATEGORICAL,
            conditionId=data.get("condition_id", ""),
            quoteToken="USDC",
            chainId=CHAIN_ID,
            volume=float(data.get("volume", 0) or 0),
            cutoffAt=None,  # Polymarket uses end_date_iso
            resolvedAt=None,
            rules=data.get("description", ""),
            tokenIds=token_ids,
            yesTokenId=yes_token_id,
            noTokenId=no_token_id,
            yesLabel="Yes" if is_binary else None,
            noLabel="No" if is_binary else None,
            resultTokenId=None,
            options=options,
            slug=data.get("market_slug"),
            image=data.get("image"),
        )


@dataclass
class Position:
    """User position in a prediction market (Polymarket-compatible)."""
    marketId: str
    marketTitle: str
    tokenId: str
    tokenName: str  # "YES" or "NO"
    shares: float
    avgPrice: float
    currentPrice: float
    value: float
    unrealizedPnl: float
    realizedPnl: float = 0.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Position":
        """Create Position from dict."""
        shares = float(data.get("shares", 0))
        avg_price = float(data.get("avgPrice", 0))
        current_price = float(data.get("currentPrice", 0))
        value = shares * current_price
        cost = shares * avg_price
        unrealized_pnl = value - cost

        return cls(
            marketId=data.get("marketId", ""),
            marketTitle=data.get("marketTitle", ""),
            tokenId=data.get("tokenId", ""),
            tokenName=data.get("tokenName", ""),
            shares=shares,
            avgPrice=avg_price,
            currentPrice=current_price,
            value=value,
            unrealizedPnl=unrealized_pnl,
            realizedPnl=float(data.get("realizedPnl", 0)),
        )


@dataclass
class Trade:
    """Trade record (Polymarket-compatible)."""
    tradeId: str
    marketId: str
    marketTitle: str
    tokenId: str
    side: int  # OrderSide
    price: float
    amount: float  # shares
    value: float  # USDC value
    timestamp: int
    tx_hash: str = ""
    is_buy: bool = True

    @classmethod
    def from_data_api(cls, data: Dict[str, Any]) -> "Trade":
        """Create Trade from Polymarket Data API response."""
        is_buy = data.get("side") == "BUY" or data.get("is_buy", False)
        price = float(data.get("price", 0))
        amount = float(data.get("size") or data.get("amount", 0))

        return cls(
            tradeId=str(data.get("id", "")),
            marketId=data.get("condition_id", ""),
            marketTitle=data.get("title") or data.get("market", ""),
            tokenId=data.get("asset_id") or data.get("token_id", ""),
            side=OrderSide.BUY if is_buy else OrderSide.SELL,
            price=price,
            amount=amount,
            value=price * amount,
            timestamp=int(data.get("timestamp") or data.get("created_at", 0)),
            tx_hash=data.get("transaction_hash") or data.get("tx_hash", ""),
            is_buy=is_buy,
        )


@dataclass
class Balance:
    """Token balance (Polymarket-compatible)."""
    token: str
    symbol: str
    available: float
    frozen: float
    total: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Balance":
        return cls(
            token=data.get("token", ""),
            symbol=data.get("symbol", ""),
            available=float(data.get("available", 0)),
            frozen=float(data.get("frozen", 0)),
            total=float(data.get("total", 0)),
        )


@dataclass
class Orderbook:
    """Market orderbook."""
    bids: List[Tuple[float, float]]  # [(price, size), ...]
    asks: List[Tuple[float, float]]

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0][0] if self.asks else None


# ============================================================================
# POLYMARKET CLIENT
# ============================================================================

class PolymarketClient:
    """
    Polymarket client matching PolymarketClient interface.

    Each user gets their own client instance with their private key.
    """

    def __init__(
        self,
        private_key: Optional[str] = None,
        funder_address: Optional[str] = None,
        signature_type: int = 1,
    ):
        """
        Initialize Polymarket client.

        Args:
            private_key: User's private key for signing
            funder_address: Proxy/funder address holding funds
            signature_type: 0=EOA, 1=proxy (default), 2=browser
        """
        self.private_key = private_key
        self.funder_address = funder_address or private_key  # Use same if not provided
        self.signature_type = signature_type
        self._clob: Optional[ClobClient] = None

    def _get_clob(self) -> Optional[ClobClient]:
        """Get or create the CLOB client."""
        if not self.private_key:
            return None

        if self._clob is None:
            try:
                self._clob = ClobClient(
                    host=CLOB_HOST,
                    key=self.private_key,
                    chain_id=CHAIN_ID,
                    signature_type=self.signature_type,
                    funder=self.funder_address,
                )
                creds = self._clob.create_or_derive_api_creds()
                self._clob.set_api_creds(creds)
            except Exception as e:
                logger.error(f"Failed to initialize CLOB client: {e}")
                return None

        return self._clob

    # ========================================================================
    # MARKET DATA METHODS
    # ========================================================================

    def get_markets(
        self,
        topic_type: Optional[int] = None,
        page: int = 1,
        limit: int = 20,
        status: Optional[str] = None,
    ) -> List[Market]:
        """Get list of prediction markets."""
        try:
            params = {
                "limit": min(limit, 100),
                "offset": (page - 1) * limit,
            }
            if status == TopicStatusFilter.ACTIVATED:
                params["active"] = "true"
            elif status == TopicStatusFilter.RESOLVED:
                params["closed"] = "true"

            r = requests.get(f"{GAMMA_API}/markets", params=params, timeout=15)
            r.raise_for_status()
            data = r.json()

            markets = []
            for item in data if isinstance(data, list) else []:
                try:
                    market = Market.from_gamma_api(item)
                    # Filter by topic type if specified
                    if topic_type is not None and market.marketType != topic_type:
                        continue
                    markets.append(market)
                except Exception as e:
                    logger.warning(f"Failed to parse market: {e}")

            return markets[:limit]

        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            return []

    def search_markets(
        self,
        keyword: str,
        max_results: int = 20,
        status: Optional[str] = TopicStatusFilter.ACTIVATED,
        use_cache: bool = True,
        max_pages: Optional[int] = None,
    ) -> List[Market]:
        """Search markets by keyword with relevance ranking."""
        global _GLOBAL_MARKETS_CACHE, _GLOBAL_MARKETS_CACHE_TIME

        # Check cache
        current_time = time.time()
        if use_cache and _GLOBAL_MARKETS_CACHE and (current_time - _GLOBAL_MARKETS_CACHE_TIME) < _CACHE_TTL:
            all_markets = _GLOBAL_MARKETS_CACHE
        else:
            # Fetch all markets
            all_markets = self.get_markets(limit=500, status=status)
            _GLOBAL_MARKETS_CACHE = all_markets
            _GLOBAL_MARKETS_CACHE_TIME = current_time

        # Score and rank by keyword match
        keyword_lower = keyword.lower()
        scored = []

        for market in all_markets:
            title_lower = market.marketTitle.lower()
            score = 0

            if title_lower == keyword_lower:
                score = 1000
            elif title_lower.startswith(keyword_lower):
                score = 800
            elif f" {keyword_lower} " in f" {title_lower} ":
                score = 600
            elif keyword_lower in title_lower:
                score = 400
            elif market.rules and keyword_lower in market.rules.lower():
                score = 200

            if score > 0:
                scored.append((score, market.volume, market))

        # Sort by score, then by volume
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [m for _, _, m in scored[:max_results]]

    def get_market(self, market_id: str, use_cache: bool = True) -> Optional[Market]:
        """Get market by condition ID."""
        try:
            r = requests.get(f"{GAMMA_API}/markets/{market_id}", timeout=15)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return Market.from_gamma_api(r.json())
        except Exception as e:
            logger.error(f"Error fetching market {market_id}: {e}")
            return None

    def get_orderbook(self, token_id: str) -> Optional[Orderbook]:
        """Get orderbook for a token."""
        clob = self._get_clob()
        if not clob:
            return None

        try:
            ob = clob.get_order_book(token_id)
            if not ob:
                return None

            bids = [(float(b.price), float(b.size)) for b in (ob.bids or [])]
            asks = [(float(a.price), float(a.size)) for a in (ob.asks or [])]
            return Orderbook(bids=bids, asks=asks)

        except Exception as e:
            logger.error(f"Error fetching orderbook: {e}")
            return None

    def get_latest_price(self, token_id: str) -> Optional[float]:
        """Get current price for a token."""
        ob = self.get_orderbook(token_id)
        if not ob:
            return None
        if ob.best_bid and ob.best_ask:
            return (ob.best_bid + ob.best_ask) / 2
        return ob.best_bid or ob.best_ask

    # ========================================================================
    # USER DATA METHODS
    # ========================================================================

    def get_my_balances(self) -> List[Balance]:
        """Get user's USDC balance (Polymarket only uses USDC)."""
        # Polymarket doesn't have a direct balance API - would need on-chain query
        # For now, return placeholder
        return [Balance(
            token="USDC",
            symbol="USDC",
            available=0.0,
            frozen=0.0,
            total=0.0,
        )]

    def get_my_positions(
        self,
        market_id: str = "",
        page: int = 1,
        limit: int = 10,
    ) -> List[Position]:
        """Get user's open positions."""
        # Polymarket doesn't have a positions API - need to calculate from trades
        # This would require tracking trades in a database
        logger.warning("Position tracking requires database - returning empty")
        return []

    def get_my_trades(
        self,
        market_id: Optional[str] = None,
        page: int = 1,
        limit: int = 10,
    ) -> List[Trade]:
        """Get user's trade history."""
        if not self.funder_address:
            return []

        try:
            params = {
                "user": self.funder_address.lower(),
                "limit": limit,
                "offset": (page - 1) * limit,
            }

            r = requests.get(f"{DATA_API}/trades", params=params, timeout=15)
            r.raise_for_status()
            data = r.json()

            trades = []
            for item in data if isinstance(data, list) else []:
                trade = Trade.from_data_api(item)
                if market_id and trade.marketId != market_id:
                    continue
                trades.append(trade)

            return trades

        except Exception as e:
            logger.error(f"Error fetching trades: {e}")
            return []

    def get_my_pnl(self) -> Dict[str, float]:
        """Calculate user's total PnL from positions."""
        positions = self.get_my_positions()
        realized = sum(p.realizedPnl for p in positions)
        unrealized = sum(p.unrealizedPnl for p in positions)
        return {
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "total_pnl": realized + unrealized,
        }

    # ========================================================================
    # TRADING OPERATIONS
    # ========================================================================

    def place_order(
        self,
        data: PlaceOrderDataInput,
        check_approval: bool = False,
    ) -> Dict[str, Any]:
        """Place a market or limit order."""
        clob = self._get_clob()
        if not clob:
            raise PolymarketError("CLOB client not initialized")

        data.validate()

        try:
            # Determine amount and side
            if data.makerAmountInQuoteToken:
                amount = float(data.makerAmountInQuoteToken)
            else:
                amount = float(data.makerAmountInBaseToken)

            side = BUY if data.side == OrderSide.BUY else SELL

            # For SELL orders, amount must be in shares
            if side == SELL and data.makerAmountInQuoteToken:
                # Convert USDC to shares
                ob = self.get_orderbook(data.tokenId)
                if not ob or not ob.best_bid:
                    raise PolymarketError("No bid price available")
                amount = float(data.makerAmountInQuoteToken) / ob.best_bid

            args = MarketOrderArgs(
                token_id=data.tokenId,
                amount=amount,
                side=side,
            )

            order = clob.create_market_order(args)
            resp = clob.post_order(order, ClobOrderType.FOK)

            # Parse response
            if isinstance(resp, dict):
                if resp.get("orderID") or resp.get("success"):
                    return {"success": True, "order_id": resp.get("orderID", "")}

            return {"success": bool(resp), "response": resp}

        except Exception as e:
            logger.error(f"Order failed: {e}")
            raise PolymarketError(str(e))

    def buy_outcome(
        self,
        market_id: str,
        outcome_index: int,
        amount_usdc: float,
    ) -> Dict[str, Any]:
        """Buy outcome tokens by index (0=YES, 1=NO for binary)."""
        market = self.get_market(market_id)
        if not market:
            raise PolymarketError(f"Market not found: {market_id}")

        if market.marketType == TopicType.BINARY:
            token_id = market.yesTokenId if outcome_index == 0 else market.noTokenId
        else:
            if not market.options or outcome_index >= len(market.options):
                raise InvalidParamError(f"Invalid outcome index: {outcome_index}")
            token_id = market.options[outcome_index].get("tokenId")

        if not token_id:
            raise PolymarketError("Could not determine token ID")

        return self.place_order(PlaceOrderDataInput(
            marketId=market_id,
            tokenId=token_id,
            side=OrderSide.BUY,
            orderType=OrderType.MARKET_ORDER,
            price="0",
            makerAmountInQuoteToken=str(amount_usdc),
        ))

    def buy_yes(self, market_id: str, amount_usdc: float) -> Dict[str, Any]:
        """Buy YES tokens on a binary market."""
        return self.buy_outcome(market_id, 0, amount_usdc)

    def buy_no(self, market_id: str, amount_usdc: float) -> Dict[str, Any]:
        """Buy NO tokens on a binary market."""
        return self.buy_outcome(market_id, 1, amount_usdc)

    def sell_position(
        self,
        position: Position,
        shares: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Sell shares from a position."""
        sell_amount = shares if shares is not None else position.shares

        return self.place_order(PlaceOrderDataInput(
            marketId=position.marketId,
            tokenId=position.tokenId,
            side=OrderSide.SELL,
            orderType=OrderType.MARKET_ORDER,
            price="0",
            makerAmountInBaseToken=str(sell_amount),
        ))

    # ========================================================================
    # STATIC METHODS (for copytrading)
    # ========================================================================

    @staticmethod
    def fetch_wallet_trades(wallet: str, limit: int = 50) -> List[Trade]:
        """Fetch trades for any wallet (for copytrading)."""
        try:
            r = requests.get(
                f"{DATA_API}/trades",
                params={"user": wallet.lower(), "limit": limit},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()

            if isinstance(data, list):
                return [Trade.from_data_api(t) for t in data]
            return []

        except Exception as e:
            logger.error(f"Error fetching trades for {wallet}: {e}")
            return []


# Backwards compatibility alias
PolymarketClient = PolymarketClient
