"""
Comprehensive unit tests for opinion.py

Tests all functions, classes, and data models in the Polymarket API client using pytest.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from decimal import Decimal
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.opinion import (
    PolymarketClient,
    Market,
    Position,
    Balance,
    Trade,
    Order,
    Orderbook,
    PlaceOrderDataInput,
    OrderData,
    TopicType,
    TopicStatus,
    TopicStatusFilter,
    OrderSide,
    OrderType,
    SignatureType,
    safe_amount_to_wei,
    wei_to_amount,
    calculate_order_amounts,
    PolymarketError,
    InvalidParamError,
    OpenApiError,
    BalanceNotEnough,
    NoPositionsToRedeem,
    InsufficientGasBalance,
    CHAIN_ID,
    USDT_DECIMALS,
)


# ============================================================================
# Test Enums
# ============================================================================

class TestEnums:
    """Test enum values."""

    def test_topic_type(self):
        """Test TopicType enum."""
        assert TopicType.BINARY == 0
        assert TopicType.CATEGORICAL == 1

    def test_topic_status(self):
        """Test TopicStatus enum."""
        assert TopicStatus.CREATED == 1
        assert TopicStatus.ACTIVATED == 2
        assert TopicStatus.RESOLVING == 3
        assert TopicStatus.RESOLVED == 4

    def test_topic_status_filter(self):
        """Test TopicStatusFilter values."""
        assert TopicStatusFilter.ALL == "all"
        assert TopicStatusFilter.ACTIVATED == "activated"
        assert TopicStatusFilter.RESOLVED == "resolved"

    def test_order_side(self):
        """Test OrderSide enum."""
        assert OrderSide.BUY == 0
        assert OrderSide.SELL == 1

    def test_order_type(self):
        """Test OrderType enum."""
        assert OrderType.MARKET_ORDER == 1
        assert OrderType.LIMIT_ORDER == 2

    def test_signature_type(self):
        """Test SignatureType enum."""
        assert SignatureType.EOA == 0
        assert SignatureType.POLY_PROXY == 1
        assert SignatureType.POLY_GNOSIS_SAFE == 2


# ============================================================================
# Test Helper Functions
# ============================================================================

class TestSafeAmountToWei:
    """Test safe_amount_to_wei function."""

    def test_convert_with_18_decimals(self):
        """Test conversion with 18 decimals."""
        assert safe_amount_to_wei(1.0, 18) == 1000000000000000000
        assert safe_amount_to_wei(0.5, 18) == 500000000000000000

    def test_convert_with_6_decimals(self):
        """Test conversion with 6 decimals."""
        assert safe_amount_to_wei(1.0, 6) == 1000000
        assert safe_amount_to_wei(100.5, 6) == 100500000

    def test_convert_zero(self):
        """Test converting zero."""
        assert safe_amount_to_wei(0, 18) == 0


class TestWeiToAmount:
    """Test wei_to_amount function."""

    def test_convert_from_wei_18_decimals(self):
        """Test conversion from wei with 18 decimals."""
        assert wei_to_amount(1000000000000000000, 18) == 1.0
        assert wei_to_amount(500000000000000000, 18) == 0.5

    def test_convert_from_wei_6_decimals(self):
        """Test conversion from wei with 6 decimals."""
        assert wei_to_amount(1000000, 6) == 1.0
        assert wei_to_amount(100500000, 6) == 100.5

    def test_convert_zero_wei(self):
        """Test converting zero wei."""
        assert wei_to_amount(0, 18) == 0.0


class TestCalculateOrderAmounts:
    """Test calculate_order_amounts function."""

    def test_buy_order_calculation(self):
        """Test BUY order amount calculation."""
        price = 0.65
        maker_amount = 1000000000000000000  # 1 USDT in wei

        maker, taker = calculate_order_amounts(price, maker_amount, OrderSide.BUY, 18)

        # For BUY: taker_amount = maker_amount / price
        # Then recalculate maker to ensure consistency
        expected_taker = int(maker_amount / price)
        expected_maker = int(expected_taker * price)

        assert maker == expected_maker
        assert taker == expected_taker

    def test_sell_order_calculation(self):
        """Test SELL order amount calculation."""
        price = 0.75
        maker_amount = 2000000000000000000  # 2 tokens in wei

        maker, taker = calculate_order_amounts(price, maker_amount, OrderSide.SELL, 18)

        # For SELL: taker_amount = maker_amount * price, maker stays same
        expected_taker = int(maker_amount * price)
        expected_maker = maker_amount

        assert maker == expected_maker
        assert taker == expected_taker


# ============================================================================
# Test Data Classes
# ============================================================================

class TestPlaceOrderDataInput:
    """Test PlaceOrderDataInput dataclass."""

    def test_create_with_quote_token(self):
        """Test creating order with quote token amount."""
        order = PlaceOrderDataInput(
            marketId=1,
            tokenId="token_yes",
            side=OrderSide.BUY,
            orderType=OrderType.LIMIT_ORDER,
            price="0.65",
            makerAmountInQuoteToken="100.0"
        )

        assert order.marketId == 1
        assert order.makerAmountInQuoteToken == "100.0"
        assert order.makerAmountInBaseToken is None

    def test_create_with_base_token(self):
        """Test creating order with base token amount."""
        order = PlaceOrderDataInput(
            marketId=2,
            tokenId="token_no",
            side=OrderSide.SELL,
            orderType=OrderType.MARKET_ORDER,
            price="0",
            makerAmountInBaseToken="1000.0"
        )

        assert order.makerAmountInBaseToken == "1000.0"
        assert order.makerAmountInQuoteToken is None

    def test_validate_with_both_amounts_fails(self):
        """Test validation fails when both amounts provided."""
        order = PlaceOrderDataInput(
            marketId=1,
            tokenId="token_yes",
            side=OrderSide.BUY,
            orderType=OrderType.LIMIT_ORDER,
            price="0.5",
            makerAmountInQuoteToken="100.0",
            makerAmountInBaseToken="200.0"
        )

        with pytest.raises(ValueError, match="exactly one"):
            order.validate()

    def test_validate_with_neither_amount_fails(self):
        """Test validation fails when neither amount provided."""
        order = PlaceOrderDataInput(
            marketId=1,
            tokenId="token_yes",
            side=OrderSide.BUY,
            orderType=OrderType.LIMIT_ORDER,
            price="0.5"
        )

        with pytest.raises(ValueError, match="exactly one"):
            order.validate()

    def test_validate_success(self):
        """Test validation succeeds with exactly one amount."""
        order = PlaceOrderDataInput(
            marketId=1,
            tokenId="token_yes",
            side=OrderSide.BUY,
            orderType=OrderType.LIMIT_ORDER,
            price="0.5",
            makerAmountInQuoteToken="100.0"
        )

        # Should not raise
        order.validate()


class TestMarket:
    """Test Market dataclass."""

    def test_from_dict(self):
        """Test creating Market from dictionary."""
        data = {
            "marketId": 1,
            "marketTitle": "BTC > $100k",
            "status": 2,
            "marketType": 0,
            "conditionId": "0x123",
            "quoteToken": "USDT",
            "chainId": 56,
            "volume": 500000.0,
            "cutoffAt": 1704067200,
            "tokenIds": ["token_yes", "token_no"]
        }

        market = Market.from_dict(data)

        assert market.marketId == 1
        assert market.marketTitle == "BTC > $100k"
        assert market.status == 2
        assert market.volume == 500000.0
        assert len(market.tokenIds) == 2

    def test_from_dict_with_missing_fields(self):
        """Test creating Market with missing optional fields."""
        data = {
            "marketId": 2,
            "marketTitle": "Test Market"
        }

        market = Market.from_dict(data)

        assert market.marketId == 2
        assert market.status == 0  # Default
        assert market.volume == 0.0  # Default
        assert market.cutoffAt is None
        assert market.tokenIds == []


class TestPosition:
    """Test Position dataclass."""

    def test_from_dict(self):
        """Test creating Position from dictionary."""
        data = {
            "marketId": 1,
            "marketTitle": "ETH > $5k",
            "tokenId": "token_yes",
            "tokenName": "YES",
            "shares": 1000.0,
            "avgPrice": 0.65,
            "currentPrice": 0.75,
            "value": 750.0,
            "unrealizedPnl": 100.0,
            "realizedPnl": 50.0
        }

        position = Position.from_dict(data)

        assert position.marketId == 1
        assert position.tokenName == "YES"
        assert position.shares == 1000.0
        assert position.unrealizedPnl == 100.0
        assert position.realizedPnl == 50.0


class TestBalance:
    """Test Balance dataclass."""

    def test_from_dict(self):
        """Test creating Balance from dictionary."""
        data = {
            "token": "USDT",
            "symbol": "USDT",
            "available": 1000.0,
            "frozen": 100.0,
            "total": 1100.0
        }

        balance = Balance.from_dict(data)

        assert balance.token == "USDT"
        assert balance.available == 1000.0
        assert balance.frozen == 100.0
        assert balance.total == 1100.0


class TestTrade:
    """Test Trade dataclass."""

    def test_from_dict(self):
        """Test creating Trade from dictionary."""
        data = {
            "tradeId": "trade_123",
            "marketId": 1,
            "tokenId": "token_yes",
            "side": 0,
            "price": 0.65,
            "amount": 100.0,
            "value": 65.0,
            "fee": 0.5,
            "timestamp": 1704067200
        }

        trade = Trade.from_dict(data)

        assert trade.tradeId == "trade_123"
        assert trade.side == 0
        assert trade.price == 0.65
        assert trade.fee == 0.5


class TestOrder:
    """Test Order dataclass."""

    def test_from_dict(self):
        """Test creating Order from dictionary."""
        data = {
            "orderId": "order_456",
            "marketId": 2,
            "tokenId": "token_no",
            "side": 1,
            "orderType": 2,
            "price": 0.45,
            "amount": 500.0,
            "filled": 250.0,
            "status": "OPEN",
            "createdAt": 1704067200
        }

        order = Order.from_dict(data)

        assert order.orderId == "order_456"
        assert order.orderType == 2
        assert order.filled == 250.0
        assert order.status == "OPEN"


class TestOrderbook:
    """Test Orderbook dataclass."""

    def test_from_dict(self):
        """Test creating Orderbook from dictionary."""
        data = {
            "bids": [
                {"price": "0.65", "amount": "1000"},
                {"price": "0.64", "amount": "2000"}
            ],
            "asks": [
                {"price": "0.66", "amount": "1500"},
                {"price": "0.67", "amount": "2500"}
            ]
        }

        orderbook = Orderbook.from_dict(data)

        assert len(orderbook.bids) == 2
        assert len(orderbook.asks) == 2
        assert orderbook.bids[0] == (0.65, 1000.0)
        assert orderbook.asks[0] == (0.66, 1500.0)


# ============================================================================
# Test PolymarketClient Initialization
# ============================================================================

class TestPolymarketClientInit:
    """Test PolymarketClient initialization."""

    @patch.dict('os.environ', {}, clear=True)
    def test_init_without_sdk(self):
        """Test initialization without SDK installed."""
        with patch.dict('sys.modules', {'opinion_clob_sdk': None}):
            client = PolymarketClient()

            assert client._client is None
            assert client.private_key is None
            assert client.api_key is None

    @patch.dict('os.environ', {'OPINION_PRIVATE_KEY': '0xtest123', 'OPINION_API_KEY': 'apikey456'})
    def test_init_from_env(self):
        """Test initialization from environment variables."""
        with patch('utils.opinion.PolymarketClobClient', create=True) as mock_sdk:
            client = PolymarketClient()

            assert client.private_key == '0xtest123'
            assert client.api_key == 'apikey456'

    def test_init_with_params(self):
        """Test initialization with explicit parameters."""
        with patch('utils.opinion.PolymarketClobClient', create=True) as mock_sdk:
            client = PolymarketClient(
                private_key='0xprivkey',
                api_key='myapikey',
                testnet=True
            )

            assert client.private_key == '0xprivkey'
            assert client.api_key == 'myapikey'
            assert client.testnet == True


# ============================================================================
# Test Market Data Methods
# ============================================================================

class TestMarketDataMethods:
    """Test market data query methods."""

    def test_get_markets_without_sdk(self):
        """Test get_markets without SDK returns mock data."""
        client = PolymarketClient()
        client._client = None

        markets = client.get_markets()

        assert len(markets) > 0
        assert isinstance(markets[0], Market)

    @patch('utils.opinion.PolymarketClobClient', create=True)
    def test_get_markets_with_sdk(self, mock_sdk_class):
        """Test get_markets with SDK."""
        mock_client = MagicMock()
        mock_client.get_markets.return_value = {
            "errno": 0,
            "result": {
                "list": [
                    {
                        "marketId": 1,
                        "marketTitle": "Test Market",
                        "status": 2,
                        "marketType": 0,
                        "conditionId": "0x123",
                        "quoteToken": "USDT",
                        "chainId": 56,
                        "volume": 10000.0,
                        "tokenIds": ["token_yes", "token_no"]
                    }
                ]
            }
        }
        mock_sdk_class.return_value = mock_client

        client = PolymarketClient(private_key="0xtest")
        markets = client.get_markets(status="activated", limit=10)

        assert len(markets) == 1
        assert markets[0].marketTitle == "Test Market"

    @patch('utils.opinion.PolymarketClobClient', create=True)
    def test_get_markets_api_error(self, mock_sdk_class):
        """Test get_markets with API error."""
        mock_client = MagicMock()
        mock_client.get_markets.return_value = {
            "errno": 1,
            "errmsg": "API Error"
        }
        mock_sdk_class.return_value = mock_client

        client = PolymarketClient(private_key="0xtest")
        markets = client.get_markets()

        # Should return empty list on error
        assert markets == []

    def test_get_market_without_sdk(self):
        """Test get_market without SDK returns mock data."""
        client = PolymarketClient()
        client._client = None

        market = client.get_market(1)

        assert market is not None
        assert isinstance(market, Market)

    @patch('utils.opinion.PolymarketClobClient', create=True)
    def test_get_orderbook_without_sdk(self, mock_sdk_class):
        """Test get_orderbook without SDK."""
        client = PolymarketClient()
        client._client = None

        orderbook = client.get_orderbook("token_yes")

        assert orderbook is not None
        assert len(orderbook.bids) > 0
        assert len(orderbook.asks) > 0

    def test_get_latest_price_without_sdk(self):
        """Test get_latest_price without SDK."""
        client = PolymarketClient()
        client._client = None

        price = client.get_latest_price("token_yes")

        assert price == 0.65


# ============================================================================
# Test User Data Methods
# ============================================================================

class TestUserDataMethods:
    """Test user data query methods."""

    def test_get_my_balances_without_sdk(self):
        """Test get_my_balances without SDK."""
        client = PolymarketClient()
        client._client = None

        balances = client.get_my_balances()

        assert len(balances) > 0
        assert isinstance(balances[0], Balance)
        assert balances[0].symbol == "USDT"

    def test_get_my_positions_without_sdk(self):
        """Test get_my_positions without SDK."""
        client = PolymarketClient()
        client._client = None

        positions = client.get_my_positions()

        assert len(positions) > 0
        assert isinstance(positions[0], Position)

    def test_get_my_pnl(self):
        """Test get_my_pnl calculation."""
        client = PolymarketClient()
        client._client = None

        pnl = client.get_my_pnl()

        assert "realized_pnl" in pnl
        assert "unrealized_pnl" in pnl
        assert "total_pnl" in pnl
        assert pnl["total_pnl"] == pnl["realized_pnl"] + pnl["unrealized_pnl"]


# ============================================================================
# Test Trading Operations
# ============================================================================

class TestTradingOperations:
    """Test trading operation methods."""

    def test_place_order_without_sdk(self):
        """Test place_order without SDK raises error."""
        client = PolymarketClient()
        client._client = None

        order = PlaceOrderDataInput(
            marketId=1,
            tokenId="token_yes",
            side=OrderSide.BUY,
            orderType=OrderType.LIMIT_ORDER,
            price="0.65",
            makerAmountInQuoteToken="100.0"
        )

        with pytest.raises(PolymarketError, match="SDK client not initialized"):
            client.place_order(order)

    @patch('utils.opinion.PolymarketClobClient', create=True)
    def test_place_order_with_sdk(self, mock_sdk_class):
        """Test place_order with SDK."""
        mock_client = MagicMock()
        mock_client.place_order.return_value = {
            "errno": 0,
            "result": {"order_id": "order_123"}
        }
        mock_sdk_class.return_value = mock_client

        client = PolymarketClient(private_key="0xtest")
        order = PlaceOrderDataInput(
            marketId=1,
            tokenId="token_yes",
            side=OrderSide.BUY,
            orderType=OrderType.LIMIT_ORDER,
            price="0.65",
            makerAmountInQuoteToken="100.0"
        )

        result = client.place_order(order)

        assert result["order_id"] == "order_123"

    @patch('utils.opinion.PolymarketClobClient', create=True)
    def test_place_order_insufficient_balance(self, mock_sdk_class):
        """Test place_order with insufficient balance."""
        mock_client = MagicMock()
        mock_client.place_order.return_value = {
            "errno": 1,
            "errmsg": "Insufficient balance"
        }
        mock_sdk_class.return_value = mock_client

        client = PolymarketClient(private_key="0xtest")
        order = PlaceOrderDataInput(
            marketId=1,
            tokenId="token_yes",
            side=OrderSide.BUY,
            orderType=OrderType.LIMIT_ORDER,
            price="0.65",
            makerAmountInQuoteToken="100.0"
        )

        with pytest.raises(BalanceNotEnough):
            client.place_order(order)


# ============================================================================
# Test Smart Contract Operations
# ============================================================================

class TestSmartContractOperations:
    """Test smart contract operation methods."""

    def test_enable_trading_without_sdk(self):
        """Test enable_trading without SDK."""
        client = PolymarketClient()
        client._client = None

        with pytest.raises(PolymarketError, match="SDK client not initialized"):
            client.enable_trading()

    @patch('utils.opinion.PolymarketClobClient', create=True)
    def test_enable_trading_with_sdk(self, mock_sdk_class):
        """Test enable_trading with SDK."""
        mock_client = MagicMock()
        mock_client.enable_trading.return_value = ("0xtxhash", {}, {})
        mock_sdk_class.return_value = mock_client

        client = PolymarketClient(private_key="0xtest")
        tx_hash, receipt, event = client.enable_trading()

        assert tx_hash == "0xtxhash"

    @patch('utils.opinion.PolymarketClobClient', create=True)
    def test_split_with_sdk(self, mock_sdk_class):
        """Test split operation."""
        mock_client = MagicMock()
        mock_client.split.return_value = ("0xsplit", {}, {})
        mock_sdk_class.return_value = mock_client

        client = PolymarketClient(private_key="0xtest")
        tx_hash, receipt, event = client.split(market_id=1, amount=100.0)

        assert tx_hash == "0xsplit"

    @patch('utils.opinion.PolymarketClobClient', create=True)
    def test_merge_with_sdk(self, mock_sdk_class):
        """Test merge operation."""
        mock_client = MagicMock()
        mock_client.merge.return_value = ("0xmerge", {}, {})
        mock_sdk_class.return_value = mock_client

        client = PolymarketClient(private_key="0xtest")
        tx_hash, receipt, event = client.merge(market_id=1, amount=50.0)

        assert tx_hash == "0xmerge"

    @patch('utils.opinion.PolymarketClobClient', create=True)
    def test_redeem_with_sdk(self, mock_sdk_class):
        """Test redeem operation."""
        mock_client = MagicMock()
        mock_client.redeem.return_value = ("0xredeem", {}, {})
        mock_sdk_class.return_value = mock_client

        client = PolymarketClient(private_key="0xtest")
        tx_hash, receipt, event = client.redeem(market_id=1)

        assert tx_hash == "0xredeem"


# ============================================================================
# Test Convenience Methods
# ============================================================================

class TestConvenienceMethods:
    """Test convenience trading methods."""

    @patch('utils.opinion.PolymarketClobClient', create=True)
    def test_buy_yes(self, mock_sdk_class):
        """Test buy_yes convenience method."""
        mock_client = MagicMock()
        mock_client.get_market.return_value = {
            "errno": 0,
            "result": {
                "data": {
                    "marketId": 1,
                    "marketTitle": "Test",
                    "status": 2,
                    "marketType": 0,
                    "conditionId": "0x123",
                    "quoteToken": "USDT",
                    "chainId": 56,
                    "volume": 1000.0,
                    "tokenIds": ["token_yes", "token_no"]
                }
            }
        }
        mock_client.place_order.return_value = {
            "errno": 0,
            "result": {"order_id": "yes_order"}
        }
        mock_sdk_class.return_value = mock_client

        client = PolymarketClient(private_key="0xtest")
        result = client.buy_yes(market_id=1, amount_usdt=100.0, price=0.65)

        assert result["order_id"] == "yes_order"

    @patch('utils.opinion.PolymarketClobClient', create=True)
    def test_buy_no(self, mock_sdk_class):
        """Test buy_no convenience method."""
        mock_client = MagicMock()
        mock_client.get_market.return_value = {
            "errno": 0,
            "result": {
                "data": {
                    "marketId": 1,
                    "marketTitle": "Test",
                    "status": 2,
                    "marketType": 0,
                    "conditionId": "0x123",
                    "quoteToken": "USDT",
                    "chainId": 56,
                    "volume": 1000.0,
                    "tokenIds": ["token_yes", "token_no"]
                }
            }
        }
        mock_client.place_order.return_value = {
            "errno": 0,
            "result": {"order_id": "no_order"}
        }
        mock_sdk_class.return_value = mock_client

        client = PolymarketClient(private_key="0xtest")
        result = client.buy_no(market_id=1, amount_usdt=50.0, price=0.35)

        assert result["order_id"] == "no_order"

    @patch('utils.opinion.PolymarketClobClient', create=True)
    def test_sell_position(self, mock_sdk_class):
        """Test sell_position convenience method."""
        mock_client = MagicMock()
        mock_client.place_order.return_value = {
            "errno": 0,
            "result": {"order_id": "sell_order"}
        }
        mock_sdk_class.return_value = mock_client

        position = Position(
            marketId=1,
            marketTitle="Test",
            tokenId="token_yes",
            tokenName="YES",
            shares=1000.0,
            avgPrice=0.65,
            currentPrice=0.75,
            value=750.0,
            unrealizedPnl=100.0
        )

        client = PolymarketClient(private_key="0xtest")
        result = client.sell_position(position, amount=500.0, price=0.70)

        assert result["order_id"] == "sell_order"


# ============================================================================
# Test Exceptions
# ============================================================================

class TestExceptions:
    """Test custom exception classes."""

    def test_opinion_error(self):
        """Test PolymarketError exception."""
        with pytest.raises(PolymarketError):
            raise PolymarketError("Test error")

    def test_invalid_param_error(self):
        """Test InvalidParamError exception."""
        with pytest.raises(InvalidParamError):
            raise InvalidParamError("Invalid params")

    def test_open_api_error(self):
        """Test OpenApiError exception."""
        with pytest.raises(OpenApiError):
            raise OpenApiError("API failed")

    def test_balance_not_enough(self):
        """Test BalanceNotEnough exception."""
        with pytest.raises(BalanceNotEnough):
            raise BalanceNotEnough("Insufficient funds")

    def test_no_positions_to_redeem(self):
        """Test NoPositionsToRedeem exception."""
        with pytest.raises(NoPositionsToRedeem):
            raise NoPositionsToRedeem("No positions")

    def test_insufficient_gas_balance(self):
        """Test InsufficientGasBalance exception."""
        with pytest.raises(InsufficientGasBalance):
            raise InsufficientGasBalance("No gas")


# ============================================================================
# Test Constants
# ============================================================================

class TestConstants:
    """Test module constants."""

    def test_chain_id(self):
        """Test CHAIN_ID constant."""
        assert CHAIN_ID == 56

    def test_usdt_decimals(self):
        """Test USDT_DECIMALS constant."""
        assert USDT_DECIMALS == 18


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
