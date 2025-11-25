"""
Opinion Prediction Market API Client

Complete implementation of Opinion's CLOB SDK for tracking positions, balances,
and executing trades on BNB Chain prediction markets.

Based on Opinion API Documentation:
- https://docs.opinion.trade/developer-guide/api-references/models
- https://docs.opinion.trade/developer-guide/api-references/methods
"""

from enum import IntEnum
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
import os
from decimal import Decimal
import time


# ============================================================================
# ENUMS
# ============================================================================

class TopicType(IntEnum):
    """Market classification types."""
    BINARY = 0  # Two-outcome markets (YES/NO)
    CATEGORICAL = 1  # Multi-outcome markets


class TopicStatus(IntEnum):
    """Market lifecycle stages."""
    CREATED = 1  # Market established but inactive
    ACTIVATED = 2  # Live and accepting trades
    RESOLVING = 3  # Ended, pending resolution
    RESOLVED = 4  # Completed with determined outcome


class TopicStatusFilter:
    """Query filter for market status."""
    ALL = "all"
    ACTIVATED = "activated"
    RESOLVED = "resolved"


class OrderSide(IntEnum):
    """Trade direction."""
    BUY = 0  # Acquire outcome tokens
    SELL = 1  # Dispose of outcome tokens


class OrderType(IntEnum):
    """Order execution methods."""
    MARKET_ORDER = 1  # Immediate execution at available prices
    LIMIT_ORDER = 2  # Execute when specified price is reached


class SignatureType(IntEnum):
    """Signature types for order authentication."""
    EOA = 0  # Externally Owned Account
    POLY_PROXY = 1  # Polygon Proxy
    POLY_GNOSIS_SAFE = 2  # Polygon Gnosis Safe


# ============================================================================
# CONSTANTS
# ============================================================================

CHAIN_ID = 56  # BNB Chain mainnet
MAX_DECIMALS = 18  # ERC20 standard
USDT_DECIMALS = 18  # USDT uses 18 decimals on Opinion
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# ============================================================================
# GLOBAL CACHE (Shared across all OpinionClient instances)
# ============================================================================

_GLOBAL_MARKETS_CACHE: Optional[List['Market']] = None
_GLOBAL_MARKETS_CACHE_TIME: float = 0
_CACHE_TTL: int = 300  # 5 minutes


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class PlaceOrderDataInput:
    """
    Order submission parameters.

    Note: Supply exactly one of makerAmountInQuoteToken or makerAmountInBaseToken.
    """
    marketId: int
    tokenId: str
    side: int  # OrderSide.BUY or OrderSide.SELL
    orderType: int  # OrderType.MARKET_ORDER or OrderType.LIMIT_ORDER
    price: str  # Price string; "0" for market orders
    makerAmountInQuoteToken: Optional[str] = None  # USDT spending amount
    makerAmountInBaseToken: Optional[str] = None  # Token quantity

    def validate(self):
        """Validate that exactly one amount field is provided."""
        has_quote = self.makerAmountInQuoteToken is not None
        has_base = self.makerAmountInBaseToken is not None

        if not (has_quote ^ has_base):  # XOR: exactly one must be True
            raise ValueError(
                "Must provide exactly one of makerAmountInQuoteToken or makerAmountInBaseToken"
            )


@dataclass
class OrderData:
    """Internal order structure with full authentication details."""
    maker: str
    taker: str
    tokenId: str
    makerAmount: str
    takerAmount: str
    side: int
    feeRateBps: int
    nonce: str
    signer: str
    expiration: str
    signatureType: int
    signature: str = ""


@dataclass
class Market:
    """Market data structure."""
    marketId: int
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
    options: Optional[List[Dict[str, Any]]] = None  # Array of {tokenId, label, ...}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Market":
        """Create Market from API response dictionary (supports both snake_case and camelCase)."""
        # Handle both snake_case (from SDK) and camelCase (legacy)
        return cls(
            marketId=data.get("market_id") or data.get("marketId", 0),
            marketTitle=data.get("market_title") or data.get("marketTitle", ""),
            status=data.get("status", 0),
            marketType=data.get("market_type") or data.get("marketType", 0),
            conditionId=data.get("condition_id") or data.get("conditionId", ""),
            quoteToken=data.get("quote_token") or data.get("quoteToken", ""),
            chainId=int(data.get("chain_id") or data.get("chainId") or CHAIN_ID),
            volume=float(data.get("volume", 0)),
            cutoffAt=data.get("cutoff_at") or data.get("cutoffAt"),
            resolvedAt=data.get("resolved_at") or data.get("resolvedAt"),
            rules=data.get("rules"),
            tokenIds=data.get("token_ids") or data.get("tokenIds", []),
            yesTokenId=data.get("yes_token_id") or data.get("yesTokenId"),
            noTokenId=data.get("no_token_id") or data.get("noTokenId"),
            yesLabel=data.get("yes_label") or data.get("yesLabel"),
            noLabel=data.get("no_label") or data.get("noLabel"),
            resultTokenId=data.get("result_token_id") or data.get("resultTokenId"),
            options=data.get("options"),
        )


@dataclass
class Position:
    """User position in a prediction market."""
    marketId: int
    marketTitle: str
    tokenId: str
    tokenName: str  # "YES" or "NO"
    shares: float  # Number of outcome tokens held
    avgPrice: float  # Average entry price
    currentPrice: float  # Current market price
    value: float  # Current value in USDT
    unrealizedPnl: float  # Unrealized profit/loss
    realizedPnl: float = 0.0  # Realized profit/loss

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Position":
        """Create Position from API response dictionary."""
        return cls(
            marketId=data.get("marketId", 0),
            marketTitle=data.get("marketTitle", ""),
            tokenId=data.get("tokenId", ""),
            tokenName=data.get("tokenName", ""),
            shares=float(data.get("shares", 0)),
            avgPrice=float(data.get("avgPrice", 0)),
            currentPrice=float(data.get("currentPrice", 0)),
            value=float(data.get("value", 0)),
            unrealizedPnl=float(data.get("unrealizedPnl", 0)),
            realizedPnl=float(data.get("realizedPnl", 0)),
        )


@dataclass
class Balance:
    """User token balance."""
    token: str
    symbol: str
    available: float
    frozen: float
    total: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Balance":
        """Create Balance from API response dictionary."""
        return cls(
            token=data.get("token", ""),
            symbol=data.get("symbol", ""),
            available=float(data.get("available", 0)),
            frozen=float(data.get("frozen", 0)),
            total=float(data.get("total", 0)),
        )


@dataclass
class Trade:
    """Trade execution record."""
    tradeId: str
    marketId: int
    tokenId: str
    side: int  # OrderSide
    price: float
    amount: float
    value: float
    fee: float
    timestamp: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Trade":
        """Create Trade from API response dictionary."""
        return cls(
            tradeId=data.get("tradeId", ""),
            marketId=data.get("marketId", 0),
            tokenId=data.get("tokenId", ""),
            side=data.get("side", 0),
            price=float(data.get("price", 0)),
            amount=float(data.get("amount", 0)),
            value=float(data.get("value", 0)),
            fee=float(data.get("fee", 0)),
            timestamp=data.get("timestamp", 0),
        )


@dataclass
class Order:
    """Order details."""
    orderId: str
    marketId: int
    tokenId: str
    side: int
    orderType: int
    price: float
    amount: float
    filled: float
    status: str
    createdAt: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Order":
        """Create Order from API response dictionary."""
        return cls(
            orderId=data.get("orderId", ""),
            marketId=data.get("marketId", 0),
            tokenId=data.get("tokenId", ""),
            side=data.get("side", 0),
            orderType=data.get("orderType", 0),
            price=float(data.get("price", 0)),
            amount=float(data.get("amount", 0)),
            filled=float(data.get("filled", 0)),
            status=data.get("status", ""),
            createdAt=data.get("createdAt", 0),
        )


@dataclass
class Orderbook:
    """Market orderbook with bids and asks."""
    bids: List[Tuple[float, float]]  # [(price, amount), ...]
    asks: List[Tuple[float, float]]  # [(price, amount), ...]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Orderbook":
        """Create Orderbook from API response dictionary."""
        bids = [(float(b["price"]), float(b["amount"])) for b in data.get("bids", [])]
        asks = [(float(a["price"]), float(a["amount"])) for a in data.get("asks", [])]
        return cls(bids=bids, asks=asks)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def safe_amount_to_wei(amount: float, decimals: int = USDT_DECIMALS) -> int:
    """
    Convert readable amounts to wei units.

    Args:
        amount: Amount in human-readable format
        decimals: Token decimals (default: 18)

    Returns:
        Integer wei representation
    """
    return int(Decimal(str(amount)) * Decimal(10 ** decimals))


def wei_to_amount(wei: int, decimals: int = USDT_DECIMALS) -> float:
    """
    Convert wei to human-readable amount.

    Args:
        wei: Amount in wei
        decimals: Token decimals (default: 18)

    Returns:
        Float amount
    """
    return float(Decimal(wei) / Decimal(10 ** decimals))


def calculate_order_amounts(
    price: float,
    maker_amount: int,
    side: int,
    decimals: int = USDT_DECIMALS
) -> Tuple[int, int]:
    """
    Compute maker/taker amounts for order.

    Args:
        price: Order price
        maker_amount: Maker amount in wei
        side: OrderSide.BUY or OrderSide.SELL
        decimals: Token decimals

    Returns:
        Tuple of (recalculated_maker, taker_amount)
    """
    if side == OrderSide.BUY:
        taker_amount = int(maker_amount / price)
        recalculated_maker = int(taker_amount * price)
    else:  # SELL
        taker_amount = int(maker_amount * price)
        recalculated_maker = maker_amount

    return recalculated_maker, taker_amount


# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================

class OpinionError(Exception):
    """Base exception for Opinion API errors."""
    pass


class InvalidParamError(OpinionError):
    """Invalid parameters provided."""
    pass


class OpenApiError(OpinionError):
    """API request error."""
    pass


class BalanceNotEnough(OpinionError):
    """Insufficient funds for operation."""
    pass


class NoPositionsToRedeem(OpinionError):
    """No winning positions available to redeem."""
    pass


class InsufficientGasBalance(OpinionError):
    """Insufficient BNB for gas fees."""
    pass


# ============================================================================
# OPINION CLIENT
# ============================================================================

class OpinionClient:
    """
    Complete Opinion API client for prediction market trading.

    Supports:
    - Market data queries
    - Position and balance tracking
    - Order placement and management
    - Smart contract operations (split, merge, redeem)
    """

    def __init__(
        self,
        private_key: Optional[str] = None,
        api_key: Optional[str] = None,
        testnet: bool = False,
    ):
        """
        Initialize Opinion client.

        Args:
            private_key: Wallet private key for signing transactions
            api_key: Optional API key for authenticated requests
            testnet: Use testnet instead of mainnet (default: False)
        """
        self.private_key = private_key or os.getenv("OPINION_PRIVATE_KEY")
        self.api_key = api_key or os.getenv("OPINION_API_KEY")
        self.testnet = testnet

        # Initialize SDK client if available
        self._client = None
        try:
            from opinion_clob_sdk import Client, CHAIN_ID_BNB_MAINNET

            # Get multisig address from env (for read-only mode when no private key)
            multisig_addr = os.getenv("MULTISIG_ADDRESS")

            # SDK default host (from Opinion docs)
            host = "https://proxy.opinion.trade:8443"

            # RPC URL for BNB Chain (required by SDK)
            rpc_url = os.getenv("RPC_URL", "https://bsc-dataseed.binance.org/")

            if self.private_key:
                self._client = Client(
                    host=host,
                    apikey=self.api_key or "",
                    private_key=self.private_key,
                    chain_id=CHAIN_ID_BNB_MAINNET,
                    rpc_url=rpc_url
                )
            elif multisig_addr:
                # Read-only mode: use dummy private key with multisig address for market data queries
                dummy_pk = '0x' + '1' * 64  # Valid 32-byte private key (not used for trading)
                self._client = Client(
                    host=host,
                    apikey=self.api_key or "",
                    private_key=dummy_pk,
                    chain_id=CHAIN_ID_BNB_MAINNET,
                    multi_sig_addr=multisig_addr,
                    rpc_url=rpc_url
                )
            else:
                print("Warning: No MULTISIG_ADDRESS found in .env - using mock data")
        except ImportError:
            print("Warning: opinion-clob-sdk not installed. Install with: pip install opinion-clob-sdk")
        except Exception as e:
            print(f"Warning: Failed to initialize Opinion SDK client: {e}")

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
        """
        Get list of prediction markets.

        Args:
            topic_type: Filter by TopicType.BINARY or TopicType.CATEGORICAL
            page: Page number (≥1)
            limit: Items per page (1-20)
            status: ACTIVATED, RESOLVED, or ALL

        Returns:
            List of Market objects (empty list if SDK not initialized)
        """
        if not self._client:
            print("Warning: Opinion SDK client not initialized - cannot fetch markets")
            return []

        try:
            # Convert our string status to SDK's TopicStatusFilter enum
            from opinion_clob_sdk import TopicStatusFilter as SDKTopicStatusFilter
            sdk_status = None
            if status:
                if status == "activated":
                    sdk_status = SDKTopicStatusFilter.ACTIVATED
                elif status == "resolved":
                    sdk_status = SDKTopicStatusFilter.RESOLVED
                elif status == "all":
                    sdk_status = None  # SDK uses None for "all"

            response = self._client.get_markets(
                topic_type=topic_type,
                page=page,
                limit=limit,
                status=sdk_status
            )

            # Response is a Pydantic model, not a dict
            if response.errno != 0:
                raise OpenApiError(f"API Error: {response.errmsg}")

            markets_data = response.result.list if response.result else []
            return [Market.from_dict(m.model_dump()) for m in markets_data]

        except Exception as e:
            print(f"Error fetching markets: {e}")
            return []

    def _get_all_active_markets(
        self,
        status: Optional[str] = "ACTIVATED",
        use_cache: bool = True,
        max_pages: Optional[int] = None
    ) -> List[Market]:
        """
        Fetch all active markets from the API with optional caching.

        This is a helper method used by search_markets to fetch all markets once
        and cache them globally for ALL users. The cache is shared across all
        OpinionClient instances.

        Performance: With 1000+ markets and limit=20, this makes 50+ API calls.
        First fetch takes ~10-15 seconds. Subsequent calls use 5-minute cache.

        IMPORTANT: This fetches BOTH BINARY and CATEGORICAL markets to ensure
        complete market coverage.

        Args:
            status: Market status filter - "ACTIVATED", "RESOLVED", or "ALL"
            use_cache: Whether to use cached data if available (default: True)
            max_pages: Optional limit on pages to fetch (for progressive loading)

        Returns:
            List of all Market objects matching the status filter
        """
        global _GLOBAL_MARKETS_CACHE, _GLOBAL_MARKETS_CACHE_TIME

        # Check cache validity
        current_time = time.time()
        cache_age = current_time - _GLOBAL_MARKETS_CACHE_TIME

        if use_cache and _GLOBAL_MARKETS_CACHE and cache_age < _CACHE_TTL:
            return _GLOBAL_MARKETS_CACHE

        # Fetch BOTH binary and categorical markets
        all_markets = []

        # Fetch BINARY markets (YES/NO)
        binary_markets = self._fetch_markets_by_type(
            topic_type=TopicType.BINARY,
            status=status,
            max_pages=max_pages
        )
        all_markets.extend(binary_markets)

        # Fetch CATEGORICAL markets (multi-outcome)
        categorical_markets = self._fetch_markets_by_type(
            topic_type=TopicType.CATEGORICAL,
            status=status,
            max_pages=max_pages
        )
        all_markets.extend(categorical_markets)

        # Only update global cache if we fetched ALL pages (not partial)
        if not max_pages:
            _GLOBAL_MARKETS_CACHE = all_markets
            _GLOBAL_MARKETS_CACHE_TIME = current_time

        return all_markets

    def _fetch_markets_by_type(
        self,
        topic_type: int,
        status: Optional[str] = "ACTIVATED",
        max_pages: Optional[int] = None
    ) -> List[Market]:
        """
        Fetch all markets of a specific type (BINARY or CATEGORICAL).

        Args:
            topic_type: TopicType.BINARY or TopicType.CATEGORICAL
            status: Market status filter - "ACTIVATED", "RESOLVED", or "ALL"
            max_pages: Optional limit on pages to fetch

        Returns:
            List of Market objects of the specified type
        """
        markets = []
        page = 1
        limit = 20  # API maximum

        while True:
            # Check if we've reached max_pages
            if max_pages and page > max_pages:
                break

            batch = self.get_markets(
                topic_type=topic_type,
                page=page,
                limit=limit,
                status=status
            )

            if not batch:
                break  # No more markets (reached end of pagination)

            markets.extend(batch)

            # If we got fewer markets than the limit, we've reached the last page
            if len(batch) < limit:
                break

            page += 1

        return markets

    def search_markets(
        self,
        keyword: str,
        max_results: int = 20,
        status: Optional[str] = "ACTIVATED",
        use_cache: bool = True,
        max_pages: Optional[int] = None
    ) -> List[Market]:
        """
        Search markets by keyword across ALL active markets with relevance ranking.

        This function fetches all markets from the API (with caching) and filters
        them based on keyword matches in the market title or rules. Since the
        Opinion API doesn't provide a native search endpoint, this method fetches
        all pages of markets and filters them locally.

        Results are ranked by relevance:
        1. Exact title matches (highest priority)
        2. Title starts with keyword
        3. Title contains keyword
        4. Rules contain keyword (lowest priority)

        The first search will fetch all markets from the API. Subsequent searches
        within 5 minutes will use cached data for better performance.

        Args:
            keyword: Search term (case-insensitive)
            max_results: Maximum number of results to return (default: 20)
            status: Market status filter - "ACTIVATED", "RESOLVED", or "ALL" (default: "ACTIVATED")
            use_cache: Whether to use cached market data (default: True)
            max_pages: Optional limit on pages to fetch (for faster initial searches, default: None = all pages)

        Returns:
            List of Market objects matching the keyword, ranked by relevance

        Example:
            >>> client = OpinionClient(private_key="0x...")
            >>> results = client.search_markets("bitcoin", max_results=10)
            >>> for market in results:
            ...     print(f"{market.marketId}: {market.marketTitle}")
        """
        keyword_lower = keyword.lower()

        # Store results with relevance scores: (score, market)
        # Higher score = more relevant
        scored_results = []

        # Fetch all active markets (with caching)
        all_markets = self._get_all_active_markets(status=status, use_cache=use_cache, max_pages=max_pages)

        # Filter and score markets by keyword relevance
        for market in all_markets:
            title_lower = market.marketTitle.lower()
            score = 0

            # Exact title match (case-insensitive)
            if title_lower == keyword_lower:
                score = 1000
            # Title starts with keyword
            elif title_lower.startswith(keyword_lower):
                score = 800
            # Title contains keyword as a whole word
            elif f" {keyword_lower} " in f" {title_lower} ":
                score = 600
            # Title contains keyword anywhere
            elif keyword_lower in title_lower:
                score = 400
            # Rules contain keyword
            elif market.rules and keyword_lower in market.rules.lower():
                score = 200

            # Add to results if score > 0
            if score > 0:
                scored_results.append((score, market))

        # Sort by score (descending) and return top results
        scored_results.sort(key=lambda x: x[0], reverse=True)

        # Extract just the market objects (discard scores)
        results = [market for score, market in scored_results[:max_results]]

        return results

    def get_market(self, market_id: int, use_cache: bool = True) -> Optional[Market]:
        """
        Get detailed market information.

        Args:
            market_id: Market ID to query
            use_cache: Whether to use cached data (default: True)

        Returns:
            Market object or None if not found or SDK not initialized
        """
        if not self._client:
            print("Warning: Opinion SDK client not initialized - cannot fetch market details")
            return None

        try:
            response = self._client.get_market(market_id=market_id, use_cache=use_cache)

            # Response is a Pydantic model, not a dict
            if response.errno != 0:
                raise OpenApiError(f"API Error: {response.errmsg}")

            market_data = response.result.data if response.result else None
            if market_data:
                return Market.from_dict(market_data.model_dump())

            return None

        except Exception as e:
            print(f"Error fetching market {market_id}: {e}")
            return None

    def get_orderbook(self, token_id: str) -> Optional[Orderbook]:
        """
        Get orderbook for a specific outcome token.

        Args:
            token_id: Token identifier (e.g., "token_yes")

        Returns:
            Orderbook object with bids and asks
        """
        if not self._client:
            return Orderbook(
                bids=[(0.65, 1000), (0.64, 2000)],
                asks=[(0.66, 1500), (0.67, 2500)]
            )

        try:
            response = self._client.get_orderbook(token_id=token_id)

            # Handle Pydantic model response
            if hasattr(response, 'errno'):
                if response.errno != 0:
                    print(f"API Error: {response.errmsg}")
                    return None

                # Access orderbook data from Pydantic response
                if hasattr(response, 'result') and hasattr(response.result, 'data'):
                    orderbook_data = response.result.data
                    if hasattr(orderbook_data, 'model_dump'):
                        return Orderbook.from_dict(orderbook_data.model_dump())
                    return None
            # Handle dict response (legacy)
            elif isinstance(response, dict):
                if response.get("errno") != 0:
                    raise OpenApiError(f"API Error: {response.get('errmsg')}")

                orderbook_data = response.get("result", {}).get("data", {})
                return Orderbook.from_dict(orderbook_data)

            return None

        except Exception as e:
            print(f"Error fetching orderbook for {token_id}: {e}")
            return None

    def get_latest_price(self, token_id: str) -> Optional[float]:
        """
        Get current price for a token.

        Args:
            token_id: Token identifier (string)

        Returns:
            Current price as float (between 0 and 1), or None on error
        """
        if not self._client:
            return None  # Return None instead of mock data to indicate API unavailable

        try:
            response = self._client.get_latest_price(token_id=token_id)

            # Check if response is successful (handle both Pydantic models and dicts)
            if hasattr(response, 'errno'):
                if response.errno != 0:
                    # API error - fallback to orderbook midpoint
                    return self._get_price_from_orderbook(token_id)

                # Access price_data from Pydantic response
                if hasattr(response, 'result') and hasattr(response.result, 'data'):
                    price = float(response.result.data.price)
                    return price if price > 0 else None
            elif isinstance(response, dict):
                # Fallback to dict access
                if response.get("errno") != 0:
                    # API error - fallback to orderbook midpoint
                    return self._get_price_from_orderbook(token_id)

                price_data = response.get("result", {}).get("data", {})
                price = float(price_data.get("price", 0))
                return price if price > 0 else None

            return None

        except Exception as e:
            print(f"Error fetching price for {token_id}: {e}")
            # Fallback to orderbook
            return self._get_price_from_orderbook(token_id)

    def _get_price_from_orderbook(self, token_id: str) -> Optional[float]:
        """
        Get price from orderbook midpoint as fallback.

        Args:
            token_id: Token identifier

        Returns:
            Midpoint price from orderbook, or None
        """
        try:
            orderbook = self.get_orderbook(token_id)
            if not orderbook or not orderbook.bids or not orderbook.asks:
                return None

            # Get best bid and ask
            best_bid = orderbook.bids[0][0] if orderbook.bids else None
            best_ask = orderbook.asks[0][0] if orderbook.asks else None

            if best_bid is not None and best_ask is not None:
                # Return midpoint price
                return (best_bid + best_ask) / 2
            elif best_bid is not None:
                return best_bid
            elif best_ask is not None:
                return best_ask

            return None
        except Exception as e:
            print(f"Error getting price from orderbook for {token_id}: {e}")
            return None

    def get_price_history(
        self,
        token_id: str,
        interval: str = "1h",
        start_at: Optional[int] = None,
        end_at: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get historical price data (OHLCV candlesticks).

        Args:
            token_id: Token identifier
            interval: Time interval (1m, 1h, 1d, 1w, max)
            start_at: Start timestamp (Unix seconds)
            end_at: End timestamp (Unix seconds)

        Returns:
            List of OHLCV candlestick data
        """
        if not self._client:
            return []

        try:
            response = self._client.get_price_history(
                token_id=token_id,
                interval=interval,
                start_at=start_at,
                end_at=end_at
            )

            if response.get("errno") != 0:
                raise OpenApiError(f"API Error: {response.get('errmsg')}")

            return response.get("result", {}).get("list", [])

        except Exception as e:
            print(f"Error fetching price history for {token_id}: {e}")
            return []

    # ========================================================================
    # USER DATA METHODS
    # ========================================================================

    def get_my_balances(self) -> List[Balance]:
        """
        Get user's token balances.

        Returns:
            List of Balance objects
        """
        if not self._client:
            return [
                Balance(
                    token="USDT",
                    symbol="USDT",
                    available=10000.0,
                    frozen=500.0,
                    total=10500.0
                )
            ]

        try:
            response = self._client.get_my_balances()

            if response.get("errno") != 0:
                raise OpenApiError(f"API Error: {response.get('errmsg')}")

            balances_data = response.get("result", {}).get("list", [])
            return [Balance.from_dict(b) for b in balances_data]

        except Exception as e:
            print(f"Error fetching balances: {e}")
            return []

    def get_my_positions(
        self,
        market_id: int = 0,
        page: int = 1,
        limit: int = 10,
    ) -> List[Position]:
        """
        Get user's open positions.

        Args:
            market_id: Filter by market (0=all)
            page: Page number
            limit: Items per page

        Returns:
            List of Position objects (empty list if SDK not initialized or no positions)
        """
        if not self._client:
            # Return empty list instead of mock data when SDK is not initialized
            print("Warning: Opinion SDK client not initialized - cannot fetch positions")
            return []

        try:
            response = self._client.get_my_positions(
                market_id=market_id,
                page=page,
                limit=limit
            )

            if response.get("errno") != 0:
                raise OpenApiError(f"API Error: {response.get('errmsg')}")

            positions_data = response.get("result", {}).get("list", [])
            return [Position.from_dict(p) for p in positions_data]

        except Exception as e:
            print(f"Error fetching positions: {e}")
            return []

    def get_my_trades(
        self,
        market_id: Optional[int] = None,
        page: int = 1,
        limit: int = 10,
    ) -> List[Trade]:
        """
        Get user's trade history.

        Args:
            market_id: Filter by market
            page: Page number
            limit: Items per page

        Returns:
            List of Trade objects
        """
        if not self._client:
            return []

        try:
            response = self._client.get_my_trades(
                market_id=market_id,
                page=page,
                limit=limit
            )

            if response.get("errno") != 0:
                raise OpenApiError(f"API Error: {response.get('errmsg')}")

            trades_data = response.get("result", {}).get("list", [])
            return [Trade.from_dict(t) for t in trades_data]

        except Exception as e:
            print(f"Error fetching trades: {e}")
            return []

    def get_my_pnl(self) -> Dict[str, float]:
        """
        Calculate user's total PnL from positions.

        Returns:
            Dictionary with realized_pnl, unrealized_pnl, total_pnl
        """
        positions = self.get_my_positions()

        realized_pnl = sum(p.realizedPnl for p in positions)
        unrealized_pnl = sum(p.unrealizedPnl for p in positions)

        return {
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "total_pnl": realized_pnl + unrealized_pnl,
        }

    # ========================================================================
    # TRADING OPERATIONS
    # ========================================================================

    def place_order(
        self,
        data: PlaceOrderDataInput,
        check_approval: bool = False,
    ) -> Dict[str, Any]:
        """
        Place a market or limit order.

        Args:
            data: PlaceOrderDataInput with order parameters
            check_approval: Auto-approve if needed

        Returns:
            Order result with order_id

        Raises:
            InvalidParamError: If parameters are invalid
            BalanceNotEnough: If insufficient funds
        """
        if not self._client:
            raise OpinionError("SDK client not initialized. Provide private_key.")

        # Validate input
        data.validate()

        try:
            response = self._client.place_order(data=data, check_approval=check_approval)

            if response.get("errno") != 0:
                error_msg = response.get("errmsg", "Unknown error")
                if "balance" in error_msg.lower():
                    raise BalanceNotEnough(error_msg)
                raise OpenApiError(f"Order failed: {error_msg}")

            return response.get("result", {})

        except Exception as e:
            print(f"Error placing order: {e}")
            raise

    def place_orders_batch(
        self,
        orders: List[PlaceOrderDataInput],
        check_approval: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Place multiple orders in a batch.

        Args:
            orders: List of PlaceOrderDataInput objects
            check_approval: Auto-approve if needed

        Returns:
            List with success/error results for each order
        """
        if not self._client:
            raise OpinionError("SDK client not initialized. Provide private_key.")

        # Validate all inputs
        for order in orders:
            order.validate()

        try:
            response = self._client.place_orders_batch(
                orders=orders,
                check_approval=check_approval
            )

            if response.get("errno") != 0:
                raise OpenApiError(f"Batch order failed: {response.get('errmsg')}")

            return response.get("result", {}).get("list", [])

        except Exception as e:
            print(f"Error placing batch orders: {e}")
            raise

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel a specific order.

        Args:
            order_id: Order identifier

        Returns:
            Cancellation confirmation
        """
        if not self._client:
            raise OpinionError("SDK client not initialized. Provide private_key.")

        try:
            response = self._client.cancel_order(order_id=order_id)

            if response.get("errno") != 0:
                raise OpenApiError(f"Cancel failed: {response.get('errmsg')}")

            return response.get("result", {})

        except Exception as e:
            print(f"Error cancelling order {order_id}: {e}")
            raise

    def cancel_all_orders(
        self,
        market_id: Optional[int] = None,
        side: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Cancel all orders, optionally filtered by market and/or side.

        Args:
            market_id: Filter by market (optional)
            side: Filter by side (optional)

        Returns:
            Dictionary with cancellation summary and detailed results
        """
        if not self._client:
            raise OpinionError("SDK client not initialized. Provide private_key.")

        try:
            response = self._client.cancel_all_orders(market_id=market_id, side=side)

            if response.get("errno") != 0:
                raise OpenApiError(f"Cancel all failed: {response.get('errmsg')}")

            return response.get("result", {})

        except Exception as e:
            print(f"Error cancelling all orders: {e}")
            raise

    def get_my_orders(
        self,
        market_id: int = 0,
        status: str = "",
        limit: int = 10,
        page: int = 1,
    ) -> List[Order]:
        """
        Get user's orders.

        Args:
            market_id: Filter by market (0=all)
            status: Filter by status ("open", "filled", etc.)
            limit: Items per page
            page: Page number

        Returns:
            List of Order objects
        """
        if not self._client:
            return []

        try:
            response = self._client.get_my_orders(
                market_id=market_id,
                status=status,
                limit=limit,
                page=page
            )

            if response.get("errno") != 0:
                raise OpenApiError(f"API Error: {response.get('errmsg')}")

            orders_data = response.get("result", {}).get("list", [])
            return [Order.from_dict(o) for o in orders_data]

        except Exception as e:
            print(f"Error fetching orders: {e}")
            return []

    # ========================================================================
    # SMART CONTRACT OPERATIONS
    # ========================================================================

    def enable_trading(self) -> Tuple[str, Any, Any]:
        """
        Enable trading by approving quote tokens.

        Required once before trading.

        Returns:
            Tuple of (tx_hash, tx_receipt, contract_event)

        Raises:
            InsufficientGasBalance: If insufficient BNB for gas
        """
        if not self._client:
            raise OpinionError("SDK client not initialized. Provide private_key.")

        try:
            return self._client.enable_trading()
        except Exception as e:
            if "gas" in str(e).lower():
                raise InsufficientGasBalance(str(e))
            raise

    def split(
        self,
        market_id: int,
        amount: float,
        check_approval: bool = True,
    ) -> Tuple[str, Any, Any]:
        """
        Split collateral into outcome tokens.

        Args:
            market_id: Market identifier
            amount: Amount in USDT (will be converted to wei)
            check_approval: Auto-enable trading if needed

        Returns:
            Tuple of (tx_hash, tx_receipt, contract_event)
        """
        if not self._client:
            raise OpinionError("SDK client not initialized. Provide private_key.")

        amount_wei = safe_amount_to_wei(amount)

        try:
            return self._client.split(
                market_id=market_id,
                amount=amount_wei,
                check_approval=check_approval
            )
        except Exception as e:
            if "balance" in str(e).lower():
                raise BalanceNotEnough(str(e))
            if "gas" in str(e).lower():
                raise InsufficientGasBalance(str(e))
            raise

    def merge(
        self,
        market_id: int,
        amount: float,
        check_approval: bool = True,
    ) -> Tuple[str, Any, Any]:
        """
        Merge outcome tokens back into collateral.

        Args:
            market_id: Market identifier
            amount: Outcome token amount (will be converted to wei)
            check_approval: Auto-enable trading if needed

        Returns:
            Transaction confirmation tuple
        """
        if not self._client:
            raise OpinionError("SDK client not initialized. Provide private_key.")

        amount_wei = safe_amount_to_wei(amount)

        try:
            return self._client.merge(
                market_id=market_id,
                amount=amount_wei,
                check_approval=check_approval
            )
        except Exception as e:
            if "balance" in str(e).lower():
                raise BalanceNotEnough(str(e))
            if "gas" in str(e).lower():
                raise InsufficientGasBalance(str(e))
            raise

    def redeem(
        self,
        market_id: int,
        check_approval: bool = True,
    ) -> Tuple[str, Any, Any]:
        """
        Redeem winning tokens after market resolution.

        Args:
            market_id: Resolved market identifier
            check_approval: Auto-enable trading if needed

        Returns:
            Transaction confirmation tuple

        Raises:
            NoPositionsToRedeem: If no winning positions
        """
        if not self._client:
            raise OpinionError("SDK client not initialized. Provide private_key.")

        try:
            return self._client.redeem(
                market_id=market_id,
                check_approval=check_approval
            )
        except Exception as e:
            if "no position" in str(e).lower():
                raise NoPositionsToRedeem(str(e))
            if "gas" in str(e).lower():
                raise InsufficientGasBalance(str(e))
            raise

    # ========================================================================
    # CONVENIENCE METHODS
    # ========================================================================

    def buy_outcome(
        self,
        market_id: int,
        outcome_index: int,
        amount_usdt: float,
        price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Buy a specific outcome token by index (works for both binary and categorical markets).

        Args:
            market_id: Market identifier
            outcome_index: Index of the outcome (0=YES/first option, 1=NO/second option, etc.)
            amount_usdt: Amount to spend in USDT
            price: Limit price (None for market order)

        Returns:
            Order result
        """
        # Get market to find token ID
        market = self.get_market(market_id)
        if not market:
            raise InvalidParamError(f"Market {market_id} not found")

        # Get token ID by index
        if not market.tokenIds or outcome_index >= len(market.tokenIds):
            raise InvalidParamError(f"Outcome index {outcome_index} not found for market {market_id}")

        token_id = market.tokenIds[outcome_index]

        order = PlaceOrderDataInput(
            marketId=market_id,
            tokenId=token_id,
            side=OrderSide.BUY,
            orderType=OrderType.LIMIT_ORDER if price else OrderType.MARKET_ORDER,
            price=str(price) if price else "0",
            makerAmountInQuoteToken=str(amount_usdt),
        )

        return self.place_order(order, check_approval=True)

    def buy_yes(
        self,
        market_id: int,
        amount_usdt: float,
        price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Convenience method to buy YES tokens (index 0).

        Args:
            market_id: Market identifier
            amount_usdt: Amount to spend in USDT
            price: Limit price (None for market order)

        Returns:
            Order result
        """
        return self.buy_outcome(market_id, 0, amount_usdt, price)

    def buy_no(
        self,
        market_id: int,
        amount_usdt: float,
        price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Convenience method to buy NO tokens (index 1).

        Args:
            market_id: Market identifier
            amount_usdt: Amount to spend in USDT
            price: Limit price (None for market order)

        Returns:
            Order result
        """
        return self.buy_outcome(market_id, 1, amount_usdt, price)

    def sell_position(
        self,
        position: Position,
        amount: Optional[float] = None,
        price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Convenience method to sell a position.

        Args:
            position: Position object to sell
            amount: Amount to sell (None = sell all)
            price: Limit price (None for market order)

        Returns:
            Order result
        """
        sell_amount = amount if amount is not None else position.shares

        order = PlaceOrderDataInput(
            marketId=position.marketId,
            tokenId=position.tokenId,
            side=OrderSide.SELL,
            orderType=OrderType.LIMIT_ORDER if price else OrderType.MARKET_ORDER,
            price=str(price) if price else "0",
            makerAmountInBaseToken=str(sell_amount),
        )

        return self.place_order(order, check_approval=True)

    # ========================================================================
    # MOCK DATA METHODS (for testing without SDK)
    # ========================================================================

    def _get_mock_markets(self) -> List[Market]:
        """Return mock markets for testing."""
        return [
            Market(
                marketId=1,
                marketTitle="BTC > $100k by EOY 2024",
                status=TopicStatus.ACTIVATED,
                marketType=TopicType.BINARY,
                conditionId="0x123",
                quoteToken="USDT",
                chainId=CHAIN_ID,
                volume=500000.0,
                tokenIds=["token_btc_yes", "token_btc_no"],
            )
        ]

    def _get_mock_market(self) -> Market:
        """Return mock market for testing."""
        return self._get_mock_markets()[0]

    def _get_mock_positions(self) -> List[Position]:
        """Return mock positions for testing."""
        return [
            Position(
                marketId=1,
                marketTitle="BTC > $100k by EOY 2024",
                tokenId="token_btc_yes",
                tokenName="YES",
                shares=1000.0,
                avgPrice=0.65,
                currentPrice=0.75,
                value=750.0,
                unrealizedPnl=100.0,
                realizedPnl=50.0,
            )
        ]


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

async def main():
    """Example usage of OpinionClient."""
    # Initialize client (requires private key for trading)
    client = OpinionClient(
        private_key=os.getenv("OPINION_PRIVATE_KEY"),
        api_key=os.getenv("OPINION_API_KEY")
    )

    # Get active markets
    markets = client.get_markets(status=TopicStatusFilter.ACTIVATED, limit=10)
    for market in markets:
        print(f"{market.marketId}: {market.marketTitle}")

    # Get user positions
    positions = client.get_my_positions()
    for pos in positions:
        print(f"{pos.marketTitle}: {pos.tokenName} @ ${pos.avgPrice:.2f}")
        print(f"  PnL: ${pos.unrealizedPnl:,.2f}")

    # Get balances
    balances = client.get_my_balances()
    for bal in balances:
        print(f"{bal.symbol}: ${bal.available:,.2f} available")

    # Calculate total PnL
    pnl_data = client.get_my_pnl()
    print(f"Total PnL: ${pnl_data['total_pnl']:,.2f}")

    # Place a buy order (example - uncomment to use)
    # result = client.buy_yes(market_id=1, amount_usdt=100.0, price=0.65)
    # print(f"Order placed: {result}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
