"""
deBridge DLN API Client for Cross-Chain Bridging and Same-Chain Swaps

This module provides integration with deBridge's DLN (deSwap Liquidity Network) API
to enable:
1. Same-chain swaps (USDT -> BNB on BSC for gas recharging)
2. Cross-chain bridging (ETH/Base -> BSC for deposits, BSC -> ETH/Base for withdrawals)

Documentation: https://docs.debridge.com/dln-details/integration-guidelines/order-creation
API Reference: https://docs.debridge.com/dln-details/api
"""

import os
import aiohttp
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from decimal import Decimal


class ChainId(Enum):
    """Supported chain IDs for deBridge."""
    ETHEREUM = 1
    BSC = 56  # BNB Chain
    POLYGON = 137
    ARBITRUM = 42161
    BASE = 8453
    OPTIMISM = 10
    AVALANCHE = 43114
    LINEA = 59144
    SOLANA = 7565164  # Solana chain ID in deBridge


class OrderStatus(Enum):
    """DLN order status states."""
    CREATED = "Created"
    FULFILLED = "Fulfilled"
    SENT_UNLOCK = "SentUnlock"
    ORDER_CANCELLED = "OrderCancelled"
    CLAIMED_UNLOCK = "ClaimedUnlock"
    CLAIMED_CANCEL = "ClaimedCancel"


@dataclass
class TokenInfo:
    """Token information."""
    address: str
    chain_id: int
    symbol: str
    name: str
    decimals: int
    logo_uri: Optional[str] = None


@dataclass
class QuoteResult:
    """DLN quote result with pricing and route information."""
    estimation_id: str
    give_token: TokenInfo
    take_token: TokenInfo
    give_amount: str
    take_amount: str
    fixed_fee: str
    percent_fee: str
    is_fulfilled: bool
    taker_address: Optional[str]
    maker_address: Optional[str]
    order_id: Optional[str]
    tx_data: Optional[Dict[str, Any]] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderTransaction:
    """Transaction data for creating a DLN order."""
    to: str  # Contract address
    data: str  # Transaction calldata
    value: str  # ETH value to send
    chain_id: int
    gas_limit: Optional[int] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderStatusResponse:
    """DLN order status response."""
    order_id: str
    status: OrderStatus
    give_chain_id: int
    take_chain_id: int
    give_token: str
    take_token: str
    give_amount: str
    take_amount: str
    maker_address: Optional[str] = None
    taker_address: Optional[str] = None
    created_tx_hash: Optional[str] = None
    fulfilled_tx_hash: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


class DeBridgeClient:
    """
    deBridge DLN API Client for cross-chain bridging and swaps.

    This client supports:
    - Same-chain swaps (e.g., USDT -> BNB on BSC)
    - Cross-chain bridging (e.g., USDC on Base -> USDT on BSC)

    Examples:
        # Same-chain swap: USDT -> BNB on BSC
        async with DeBridgeClient() as client:
            quote = await client.get_quote(
                src_chain_id=56,
                src_token="0x55d398326f99059fF775485246999027B3197955",  # USDT
                dst_chain_id=56,
                dst_token="0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",  # BNB
                src_amount="10000000000000000000",  # 10 USDT
                src_address="0x..."
            )

        # Cross-chain bridge: USDC on Base -> USDT on BSC
        async with DeBridgeClient() as client:
            quote = await client.get_quote(
                src_chain_id=8453,  # Base
                src_token="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC
                dst_chain_id=56,  # BSC
                dst_token="0x55d398326f99059fF775485246999027B3197955",  # USDT
                src_amount="100000000",  # 100 USDC
                src_address="0x..."
            )
    """

    # deBridge API endpoints
    API_URL = "https://api.dln.trade/v1.0"

    # Native token address (used for ETH, BNB, etc.)
    NATIVE_TOKEN = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

    # Common token addresses
    USDT_BSC = "0x55d398326f99059fF775485246999027B3197955"
    USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    USDC_ETH = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    USDC_OPTIMISM = "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85"
    USDC_ARBITRUM = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize deBridge DLN API client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the deBridge API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON body data

        Returns:
            API response as dictionary

        Raises:
            aiohttp.ClientError: If request fails
        """
        session = await self._get_session()
        url = f"{self.API_URL}{endpoint}"

        for attempt in range(self.max_retries):
            try:
                async with session.request(
                    method,
                    url,
                    params=params,
                    json=json_data
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data

            except aiohttp.ClientResponseError as e:
                if e.status >= 500 and attempt < self.max_retries - 1:
                    # Retry on server errors
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except aiohttp.ClientError as e:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise

    async def get_supported_chains(self) -> List[Dict[str, Any]]:
        """
        Get list of supported chains.

        Returns:
            List of supported chains with metadata
        """
        data = await self._request("GET", "/chain/list")
        return data.get("chains", [])

    async def get_token_list(
        self,
        chain_id: Optional[int] = None
    ) -> List[TokenInfo]:
        """
        Get list of supported tokens.

        Args:
            chain_id: Filter by specific chain ID (optional)

        Returns:
            List of supported tokens
        """
        params = {}
        if chain_id:
            params["chainId"] = chain_id

        data = await self._request("GET", "/token/list", params=params)

        tokens = []
        for token_data in data.get("tokens", []):
            tokens.append(TokenInfo(
                address=token_data.get("address", ""),
                chain_id=token_data.get("chainId", 0),
                symbol=token_data.get("symbol", ""),
                name=token_data.get("name", ""),
                decimals=token_data.get("decimals", 18),
                logo_uri=token_data.get("logoURI")
            ))

        return tokens

    async def get_quote(
        self,
        src_chain_id: int,
        src_token: str,
        dst_chain_id: int,
        dst_token: str,
        src_amount: str,
        src_address: str,
        dst_address: Optional[str] = None,
        prepend_operating_expenses: bool = False
    ) -> QuoteResult:
        """
        Get a quote for bridging/swapping tokens.

        Args:
            src_chain_id: Source chain ID
            src_token: Source token address (use NATIVE_TOKEN for ETH/BNB)
            dst_chain_id: Destination chain ID
            dst_token: Destination token address
            src_amount: Amount to send (in wei/smallest unit)
            src_address: Sender's wallet address
            dst_address: Recipient's wallet address (defaults to src_address)
            prepend_operating_expenses: Include operating expenses in quote

        Returns:
            Quote with pricing and route information

        Example:
            # Same-chain swap: 10 USDT -> BNB on BSC
            quote = await client.get_quote(
                src_chain_id=56,
                src_token="0x55d398326f99059fF775485246999027B3197955",
                dst_chain_id=56,
                dst_token=DeBridgeClient.NATIVE_TOKEN,
                src_amount="10000000000000000000",  # 10 USDT
                src_address="0x..."
            )
        """
        params = {
            "srcChainId": src_chain_id,
            "srcChainTokenIn": src_token,
            "dstChainId": dst_chain_id,
            "dstChainTokenOut": dst_token,
            "srcChainTokenInAmount": src_amount,
            "srcChainOrderAuthorityAddress": src_address,
            "dstChainTokenOutRecipient": dst_address or src_address,
            "prependOperatingExpenses": str(prepend_operating_expenses).lower()
        }

        data = await self._request("GET", "/dln/order/quote", params=params)

        # Parse response
        estimation = data.get("estimation", {})

        return QuoteResult(
            estimation_id=data.get("estimationId", ""),
            give_token=self._parse_token_info(estimation.get("srcChainTokenIn", {})),
            take_token=self._parse_token_info(estimation.get("dstChainTokenOut", {})),
            give_amount=estimation.get("srcChainTokenIn", {}).get("amount", "0"),
            take_amount=estimation.get("dstChainTokenOut", {}).get("amount", "0"),
            fixed_fee=estimation.get("fixedFee", "0"),
            percent_fee=estimation.get("percentFee", "0"),
            is_fulfilled=data.get("isFulfilled", False),
            taker_address=data.get("takerAddress"),
            maker_address=data.get("makerAddress"),
            order_id=data.get("orderId"),
            tx_data=data.get("tx"),
            raw_data=data
        )

    def _parse_token_info(self, token_data: Dict[str, Any]) -> TokenInfo:
        """Parse token info from API response."""
        return TokenInfo(
            address=token_data.get("address", ""),
            chain_id=token_data.get("chainId", 0),
            symbol=token_data.get("symbol", ""),
            name=token_data.get("name", ""),
            decimals=token_data.get("decimals", 18),
            logo_uri=token_data.get("logoURI")
        )

    async def create_order(
        self,
        src_chain_id: int,
        src_token: str,
        dst_chain_id: int,
        dst_token: str,
        src_amount: str,
        src_address: str,
        dst_address: Optional[str] = None,
        affiliate_fee_percent: Optional[str] = None,
        affiliate_fee_recipient: Optional[str] = None
    ) -> OrderTransaction:
        """
        Create a DLN order transaction.

        Args:
            src_chain_id: Source chain ID
            src_token: Source token address
            dst_chain_id: Destination chain ID
            dst_token: Destination token address
            src_amount: Amount to send
            src_address: Sender's wallet address
            dst_address: Recipient's wallet address (optional)
            affiliate_fee_percent: Affiliate fee percentage (optional)
            affiliate_fee_recipient: Affiliate fee recipient address (optional)

        Returns:
            Transaction data to sign and send

        Example:
            tx = await client.create_order(
                src_chain_id=56,
                src_token=DeBridgeClient.USDT_BSC,
                dst_chain_id=56,
                dst_token=DeBridgeClient.NATIVE_TOKEN,
                src_amount="10000000000000000000",
                src_address="0x..."
            )
            # Sign and send tx.data to tx.to
        """
        params = {
            "srcChainId": src_chain_id,
            "srcChainTokenIn": src_token,
            "dstChainId": dst_chain_id,
            "dstChainTokenOut": dst_token,
            "srcChainTokenInAmount": src_amount,
            "srcChainOrderAuthorityAddress": src_address,
            "dstChainTokenOutRecipient": dst_address or src_address
        }

        if affiliate_fee_percent:
            params["affiliateFeePercent"] = affiliate_fee_percent
        if affiliate_fee_recipient:
            params["affiliateFeeRecipient"] = affiliate_fee_recipient

        data = await self._request("GET", "/dln/order/create-tx", params=params)

        tx_data = data.get("tx", {})

        return OrderTransaction(
            to=tx_data.get("to", ""),
            data=tx_data.get("data", ""),
            value=tx_data.get("value", "0"),
            chain_id=src_chain_id,
            gas_limit=None,  # Will be estimated by wallet
            raw_data=data
        )

    async def get_order_status(self, order_id: str) -> OrderStatusResponse:
        """
        Get the status of a DLN order.

        Args:
            order_id: Order ID from quote or transaction

        Returns:
            Order status information

        Example:
            status = await client.get_order_status("0x123...")
            if status.status == OrderStatus.FULFILLED:
                print("Order completed!")
        """
        params = {"orderId": order_id}
        data = await self._request("GET", "/dln/order", params=params)

        order_data = data.get("order", {})

        # Parse status
        status_str = order_data.get("status", "Created")
        try:
            status = OrderStatus(status_str)
        except ValueError:
            status = OrderStatus.CREATED

        return OrderStatusResponse(
            order_id=order_data.get("orderId", order_id),
            status=status,
            give_chain_id=order_data.get("giveChainId", 0),
            take_chain_id=order_data.get("takeChainId", 0),
            give_token=order_data.get("giveTokenAddress", ""),
            take_token=order_data.get("takeTokenAddress", ""),
            give_amount=order_data.get("giveAmount", "0"),
            take_amount=order_data.get("takeAmount", "0"),
            maker_address=order_data.get("makerAddress"),
            taker_address=order_data.get("takerAddress"),
            created_tx_hash=order_data.get("createdTxHash"),
            fulfilled_tx_hash=order_data.get("fulfilledTxHash"),
            raw_data=order_data
        )

    async def wait_for_fulfillment(
        self,
        order_id: str,
        poll_interval: int = 10,
        max_wait_time: int = 1800  # 30 minutes
    ) -> OrderStatusResponse:
        """
        Wait for a DLN order to be fulfilled.

        Args:
            order_id: Order ID to monitor
            poll_interval: Seconds between status checks
            max_wait_time: Maximum seconds to wait

        Returns:
            Final order status

        Raises:
            TimeoutError: If order doesn't complete within max_wait_time
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            status = await self.get_order_status(order_id)

            if status.status in [OrderStatus.FULFILLED, OrderStatus.CLAIMED_UNLOCK]:
                return status
            elif status.status in [OrderStatus.ORDER_CANCELLED, OrderStatus.CLAIMED_CANCEL]:
                raise ValueError(f"Order was cancelled: {order_id}")

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_wait_time:
                raise TimeoutError(
                    f"Order did not complete within {max_wait_time}s: {order_id}"
                )

            await asyncio.sleep(poll_interval)


# Convenience functions for common operations

async def swap_usdt_to_bnb_on_bsc(
    client: DeBridgeClient,
    usdt_amount: str,
    user_address: str
) -> tuple[QuoteResult, OrderTransaction]:
    """
    Convenience function to swap USDT to BNB on BSC (for gas recharging).

    Args:
        client: DeBridgeClient instance
        usdt_amount: Amount of USDT to swap (in wei, 18 decimals)
        user_address: User's wallet address

    Returns:
        Tuple of (quote, transaction_data)

    Example:
        async with DeBridgeClient() as client:
            quote, tx = await swap_usdt_to_bnb_on_bsc(
                client=client,
                usdt_amount="10000000000000000000",  # 10 USDT
                user_address="0x..."
            )
            # Sign and send tx
    """
    # Get quote
    quote = await client.get_quote(
        src_chain_id=ChainId.BSC.value,
        src_token=DeBridgeClient.USDT_BSC,
        dst_chain_id=ChainId.BSC.value,
        dst_token=DeBridgeClient.NATIVE_TOKEN,  # BNB
        src_amount=usdt_amount,
        src_address=user_address
    )

    # Create order transaction
    tx = await client.create_order(
        src_chain_id=ChainId.BSC.value,
        src_token=DeBridgeClient.USDT_BSC,
        dst_chain_id=ChainId.BSC.value,
        dst_token=DeBridgeClient.NATIVE_TOKEN,
        src_amount=usdt_amount,
        src_address=user_address
    )

    return quote, tx


async def estimate_bnb_from_usdt(
    client: DeBridgeClient,
    usdt_amount: str,
    user_address: str
) -> str:
    """
    Estimate how much BNB will be received for a given USDT amount on BSC.

    Args:
        client: DeBridgeClient instance
        usdt_amount: Amount of USDT (in wei, 18 decimals)
        user_address: User's wallet address

    Returns:
        Estimated BNB amount (in wei)

    Example:
        bnb_amount = await estimate_bnb_from_usdt(
            client=client,
            usdt_amount="10000000000000000000",  # 10 USDT
            user_address="0x..."
        )
    """
    quote = await client.get_quote(
        src_chain_id=ChainId.BSC.value,
        src_token=DeBridgeClient.USDT_BSC,
        dst_chain_id=ChainId.BSC.value,
        dst_token=DeBridgeClient.NATIVE_TOKEN,
        src_amount=usdt_amount,
        src_address=user_address
    )

    return quote.take_amount
