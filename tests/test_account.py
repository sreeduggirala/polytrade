"""
Comprehensive unit tests for account.py

Tests all functions and classes in the account management module using pytest.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from decimal import Decimal
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.account import (
    AccountManager,
    to_wei,
    from_wei,
    format_address,
    AccountError,
    InsufficientBalance,
    InsufficientGasBalance,
    InvalidPrivateKey,
    TransactionFailed,
    create_new_account,
    load_account,
    CHAIN_ID,
    TESTNET_CHAIN_ID,
    MAINNET_RPC,
    TESTNET_RPC,
    OPINION_USDT_ADDRESS,
    DEFAULT_GAS_LIMIT,
    USDT_DECIMALS,
    BNB_DECIMALS,
)


# ============================================================================
# Test Helper Functions
# ============================================================================

class TestToWei:
    """Test to_wei conversion function."""

    def test_to_wei_with_18_decimals(self):
        """Test conversion with 18 decimals (default)."""
        assert to_wei(1.0, 18) == 1000000000000000000
        assert to_wei(0.5, 18) == 500000000000000000
        assert to_wei(10.25, 18) == 10250000000000000000

    def test_to_wei_with_6_decimals(self):
        """Test conversion with 6 decimals."""
        assert to_wei(1.0, 6) == 1000000
        assert to_wei(100.50, 6) == 100500000
        assert to_wei(0.000001, 6) == 1

    def test_to_wei_with_zero(self):
        """Test conversion of zero."""
        assert to_wei(0, 18) == 0
        assert to_wei(0.0, 6) == 0

    def test_to_wei_precision(self):
        """Test precision handling with Decimal."""
        # Use string to preserve exact precision (floats can't represent this exactly)
        result = to_wei(Decimal("1.123456789012345678"), 18)
        expected = 1123456789012345678
        assert result == expected


class TestFromWei:
    """Test from_wei conversion function."""

    def test_from_wei_with_18_decimals(self):
        """Test conversion from wei with 18 decimals."""
        assert from_wei(1000000000000000000, 18) == 1.0
        assert from_wei(500000000000000000, 18) == 0.5
        assert from_wei(10250000000000000000, 18) == 10.25

    def test_from_wei_with_6_decimals(self):
        """Test conversion from wei with 6 decimals."""
        assert from_wei(1000000, 6) == 1.0
        assert from_wei(100500000, 6) == 100.5

    def test_from_wei_with_zero(self):
        """Test conversion of zero."""
        assert from_wei(0, 18) == 0.0
        assert from_wei(0, 6) == 0.0


class TestFormatAddress:
    """Test format_address function."""

    @patch('utils.account.Web3.to_checksum_address')
    def test_format_address_basic(self, mock_checksum):
        """Test address formatting."""
        mock_checksum.return_value = "0xAbC123..."
        result = format_address("0xabc123...")

        assert result == "0xAbC123..."
        mock_checksum.assert_called_once_with("0xabc123...")

    @patch('utils.account.Web3.to_checksum_address')
    def test_format_address_without_0x(self, mock_checksum):
        """Test formatting address without 0x prefix."""
        mock_checksum.return_value = "0xAbC123..."
        result = format_address("abc123...")

        mock_checksum.assert_called_once_with("abc123...")


# ============================================================================
# Test AccountManager Initialization
# ============================================================================

class TestAccountManagerInit:
    """Test AccountManager initialization."""

    @patch('utils.account.Web3')
    def test_init_default_mainnet(self, mock_web3_class):
        """Test initialization with default mainnet settings."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_class.return_value = mock_w3

        manager = AccountManager()

        assert manager.rpc_url == MAINNET_RPC
        assert manager.testnet == False
        assert manager.chain_id == CHAIN_ID
        assert manager.account is None

    @patch('utils.account.Web3')
    def test_init_testnet(self, mock_web3_class):
        """Test initialization with testnet."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_class.return_value = mock_w3

        manager = AccountManager(testnet=True)

        assert manager.rpc_url == TESTNET_RPC
        assert manager.testnet == True
        assert manager.chain_id == TESTNET_CHAIN_ID

    @patch('utils.account.Web3')
    def test_init_with_custom_rpc(self, mock_web3_class):
        """Test initialization with custom RPC URL."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_class.return_value = mock_w3

        custom_rpc = "https://custom-rpc.example.com"
        manager = AccountManager(rpc_url=custom_rpc)

        assert manager.rpc_url == custom_rpc

    @patch('utils.account.Web3')
    def test_init_connection_failure(self, mock_web3_class):
        """Test initialization fails when RPC connection fails."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = False
        mock_web3_class.return_value = mock_w3

        with pytest.raises(AccountError, match="Failed to connect to RPC"):
            AccountManager()

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_init_with_private_key(self, mock_from_key, mock_web3_class):
        """Test initialization with private key."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_class.return_value = mock_w3

        mock_account = MagicMock()
        mock_account.address = "0x123..."
        mock_from_key.return_value = mock_account

        manager = AccountManager(private_key="0xabc123...")

        assert manager.account is not None
        mock_from_key.assert_called_once()


# ============================================================================
# Test Account Creation & Import
# ============================================================================

class TestAccountCreation:
    """Test account creation and import methods."""

    @patch('utils.account.Web3')
    @patch('utils.account.secrets.token_hex')
    @patch('utils.account.EthAccount.from_key')
    def test_create_account(self, mock_from_key, mock_token_hex, mock_web3_class):
        """Test creating a new account."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_class.return_value = mock_w3

        mock_token_hex.return_value = "abc123def456"
        mock_account = MagicMock()
        mock_account.address = "0x1234567890AbCdEf"
        mock_from_key.return_value = mock_account

        manager = AccountManager()
        result = manager.create_account()

        assert "address" in result
        assert "private_key" in result
        assert result["address"] == "0x1234567890AbCdEf"
        assert result["private_key"] == "0xabc123def456"
        assert manager.account is not None

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_import_account_with_0x_prefix(self, mock_from_key, mock_web3_class):
        """Test importing account with 0x prefix."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_class.return_value = mock_w3

        mock_account = MagicMock()
        mock_account.address = "0xImported123"
        mock_from_key.return_value = mock_account

        manager = AccountManager()
        address = manager.import_account("0xprivatekey123")

        assert address == "0xImported123"
        assert manager.account is not None
        mock_from_key.assert_called_once_with("0xprivatekey123")

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_import_account_without_0x_prefix(self, mock_from_key, mock_web3_class):
        """Test importing account without 0x prefix."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_class.return_value = mock_w3

        mock_account = MagicMock()
        mock_account.address = "0xImported456"
        mock_from_key.return_value = mock_account

        manager = AccountManager()
        address = manager.import_account("privatekey456")

        assert address == "0xImported456"
        mock_from_key.assert_called_once_with("0xprivatekey456")

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_import_account_invalid_key(self, mock_from_key, mock_web3_class):
        """Test importing with invalid private key."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_class.return_value = mock_w3

        mock_from_key.side_effect = Exception("Invalid key")

        manager = AccountManager()

        with pytest.raises(InvalidPrivateKey, match="Invalid private key format"):
            manager.import_account("invalid_key")

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_export_private_key(self, mock_from_key, mock_web3_class):
        """Test exporting private key."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_class.return_value = mock_w3

        mock_account = MagicMock()
        mock_account.address = "0xTest"
        mock_account.key.hex.return_value = "0xexportedkey123"
        mock_from_key.return_value = mock_account

        manager = AccountManager(private_key="0xtest123")
        exported_key = manager.export_private_key()

        assert exported_key == "0xexportedkey123"

    @patch('utils.account.Web3')
    def test_export_private_key_no_account(self, mock_web3_class):
        """Test exporting private key without loaded account."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_class.return_value = mock_w3

        manager = AccountManager()

        with pytest.raises(AccountError, match="No account loaded"):
            manager.export_private_key()

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_get_address(self, mock_from_key, mock_web3_class):
        """Test getting account address."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_class.return_value = mock_w3

        mock_account = MagicMock()
        mock_account.address = "0xTestAddress"
        mock_from_key.return_value = mock_account

        manager = AccountManager(private_key="0xtest")
        address = manager.get_address()

        assert address == "0xTestAddress"

    @patch('utils.account.Web3')
    def test_get_address_no_account(self, mock_web3_class):
        """Test getting address without loaded account."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_class.return_value = mock_w3

        manager = AccountManager()

        with pytest.raises(AccountError, match="No account loaded"):
            manager.get_address()


# ============================================================================
# Test Balance Queries
# ============================================================================

class TestBalanceQueries:
    """Test balance query methods."""

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_get_bnb_balance(self, mock_from_key, mock_web3_class):
        """Test getting BNB balance."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.get_balance.return_value = 5000000000000000000  # 5 BNB in wei
        mock_web3_class.return_value = mock_w3

        mock_account = MagicMock()
        mock_account.address = "0xTest"
        mock_from_key.return_value = mock_account

        manager = AccountManager(private_key="0xtest")
        balance = manager.get_bnb_balance()

        assert balance == 5.0

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_get_token_balance(self, mock_from_key, mock_web3_class):
        """Test getting ERC20 token balance."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_class.return_value = mock_w3

        # Mock contract
        mock_contract = MagicMock()
        mock_contract.functions.balanceOf.return_value.call.return_value = 1000000000000000000  # 1 token
        mock_contract.functions.decimals.return_value.call.return_value = 18
        mock_w3.eth.contract.return_value = mock_contract

        mock_account = MagicMock()
        mock_account.address = "0xTest"
        mock_from_key.return_value = mock_account

        manager = AccountManager(private_key="0xtest")
        balance = manager.get_token_balance("0xTokenAddress")

        assert balance == 1.0

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_get_usdt_balance(self, mock_from_key, mock_web3_class):
        """Test getting USDT balance."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_class.return_value = mock_w3

        mock_contract = MagicMock()
        mock_contract.functions.balanceOf.return_value.call.return_value = 100000000000000000000  # 100 USDT
        mock_contract.functions.decimals.return_value.call.return_value = 18
        mock_w3.eth.contract.return_value = mock_contract

        mock_account = MagicMock()
        mock_account.address = "0xTest"
        mock_from_key.return_value = mock_account

        manager = AccountManager(private_key="0xtest")
        balance = manager.get_usdt_balance()

        assert balance == 100.0

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_get_all_balances(self, mock_from_key, mock_web3_class):
        """Test getting all balances."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.get_balance.return_value = 2000000000000000000  # 2 BNB
        mock_web3_class.return_value = mock_w3

        mock_contract = MagicMock()
        mock_contract.functions.balanceOf.return_value.call.return_value = 50000000000000000000  # 50 USDT
        mock_contract.functions.decimals.return_value.call.return_value = 18
        mock_w3.eth.contract.return_value = mock_contract

        mock_account = MagicMock()
        mock_account.address = "0xTest"
        mock_from_key.return_value = mock_account

        manager = AccountManager(private_key="0xtest")
        balances = manager.get_all_balances()

        assert "bnb" in balances
        assert "usdt" in balances
        assert balances["bnb"] == 2.0
        assert balances["usdt"] == 50.0


# ============================================================================
# Test Token Approval
# ============================================================================

class TestTokenApproval:
    """Test token approval methods."""

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_get_allowance(self, mock_from_key, mock_web3_class):
        """Test getting token allowance."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_web3_class.return_value = mock_w3

        mock_contract = MagicMock()
        mock_contract.functions.allowance.return_value.call.return_value = 1000000000000000000
        mock_contract.functions.decimals.return_value.call.return_value = 18
        mock_w3.eth.contract.return_value = mock_contract

        mock_account = MagicMock()
        mock_account.address = "0xOwner"
        mock_from_key.return_value = mock_account

        manager = AccountManager(private_key="0xtest")
        allowance = manager.get_allowance("0xToken", "0xSpender")

        assert allowance == 1.0

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_approve_token_success(self, mock_from_key, mock_web3_class):
        """Test successful token approval."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.gas_price = 5000000000
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.get_balance.return_value = 1000000000000000000  # 1 BNB
        mock_w3.eth.send_raw_transaction.return_value.hex.return_value = "0xtxhash123"
        mock_web3_class.return_value = mock_w3

        mock_contract = MagicMock()
        mock_contract.functions.decimals.return_value.call.return_value = 18
        mock_contract.functions.approve.return_value.build_transaction.return_value = {
            "from": "0xTest",
            "chainId": CHAIN_ID,
            "gas": 50000,
            "gasPrice": 5000000000,
            "nonce": 0
        }
        mock_w3.eth.contract.return_value = mock_contract

        mock_account = MagicMock()
        mock_account.address = "0xTest"
        mock_account.sign_transaction.return_value = MagicMock(raw_transaction=b"signed_tx")
        mock_from_key.return_value = mock_account

        manager = AccountManager(private_key="0xtest")
        tx_hash = manager.approve_token("0xToken", "0xSpender", amount=100.0)

        assert tx_hash == "0xtxhash123"

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_approve_token_insufficient_gas(self, mock_from_key, mock_web3_class):
        """Test token approval with insufficient gas."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.gas_price = 5000000000
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.get_balance.return_value = 1000  # Very low balance
        mock_web3_class.return_value = mock_w3

        mock_contract = MagicMock()
        mock_contract.functions.decimals.return_value.call.return_value = 18
        mock_contract.functions.approve.return_value.build_transaction.return_value = {
            "from": "0xTest",
            "chainId": CHAIN_ID,
            "gas": 50000,
            "gasPrice": 5000000000,
            "nonce": 0
        }
        mock_w3.eth.contract.return_value = mock_contract

        mock_account = MagicMock()
        mock_account.address = "0xTest"
        mock_from_key.return_value = mock_account

        manager = AccountManager(private_key="0xtest")

        with pytest.raises(InsufficientGasBalance):
            manager.approve_token("0xToken", "0xSpender", amount=100.0)


# ============================================================================
# Test Transfers
# ============================================================================

class TestTransfers:
    """Test transfer methods."""

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_transfer_token_success(self, mock_from_key, mock_web3_class):
        """Test successful token transfer."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.gas_price = 5000000000
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.get_balance.return_value = 1000000000000000000
        mock_w3.eth.send_raw_transaction.return_value.hex.return_value = "0xtxhash456"
        mock_web3_class.return_value = mock_w3

        mock_contract = MagicMock()
        mock_contract.functions.decimals.return_value.call.return_value = 18
        mock_contract.functions.balanceOf.return_value.call.return_value = 10000000000000000000  # 10 tokens
        mock_contract.functions.transfer.return_value.build_transaction.return_value = {
            "from": "0xTest",
            "chainId": CHAIN_ID,
            "gas": DEFAULT_GAS_LIMIT,
            "gasPrice": 5000000000,
            "nonce": 0
        }
        mock_w3.eth.contract.return_value = mock_contract

        mock_account = MagicMock()
        mock_account.address = "0xTest"
        mock_account.sign_transaction.return_value = MagicMock(raw_transaction=b"signed_tx")
        mock_from_key.return_value = mock_account

        manager = AccountManager(private_key="0xtest")
        tx_hash = manager.transfer_token("0xToken", "0xRecipient", 5.0)

        assert tx_hash == "0xtxhash456"

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_transfer_token_insufficient_balance(self, mock_from_key, mock_web3_class):
        """Test token transfer with insufficient balance."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.gas_price = 5000000000
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_web3_class.return_value = mock_w3

        mock_contract = MagicMock()
        mock_contract.functions.decimals.return_value.call.return_value = 18
        mock_contract.functions.balanceOf.return_value.call.return_value = 1000000000000000000  # 1 token
        mock_w3.eth.contract.return_value = mock_contract

        mock_account = MagicMock()
        mock_account.address = "0xTest"
        mock_from_key.return_value = mock_account

        manager = AccountManager(private_key="0xtest")

        with pytest.raises(InsufficientBalance):
            manager.transfer_token("0xToken", "0xRecipient", 5.0)


# ============================================================================
# Test Transaction Utilities
# ============================================================================

class TestTransactionUtilities:
    """Test transaction utility methods."""

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_wait_for_transaction_success(self, mock_from_key, mock_web3_class):
        """Test waiting for successful transaction."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.wait_for_transaction_receipt.return_value = {"status": 1, "blockNumber": 12345}
        mock_web3_class.return_value = mock_w3

        mock_account = MagicMock()
        mock_account.address = "0xTest"
        mock_from_key.return_value = mock_account

        manager = AccountManager(private_key="0xtest")
        receipt = manager.wait_for_transaction("0xtxhash")

        assert receipt["status"] == 1
        assert receipt["blockNumber"] == 12345

    @patch('utils.account.Web3')
    @patch('utils.account.EthAccount.from_key')
    def test_wait_for_transaction_failure(self, mock_from_key, mock_web3_class):
        """Test waiting for failed transaction."""
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.wait_for_transaction_receipt.return_value = {"status": 0}
        mock_web3_class.return_value = mock_w3

        mock_account = MagicMock()
        mock_account.address = "0xTest"
        mock_from_key.return_value = mock_account

        manager = AccountManager(private_key="0xtest")

        with pytest.raises(TransactionFailed, match="reverted"):
            manager.wait_for_transaction("0xtxhash")


# ============================================================================
# Test Convenience Functions
# ============================================================================

class TestConvenienceFunctions:
    """Test module convenience functions."""

    @patch('utils.account.AccountManager')
    def test_create_new_account(self, mock_manager_class):
        """Test create_new_account convenience function."""
        mock_manager = MagicMock()
        mock_manager.create_account.return_value = {
            "address": "0xNew",
            "private_key": "0xKey"
        }
        mock_manager_class.return_value = mock_manager

        manager, info = create_new_account(testnet=False)

        assert info["address"] == "0xNew"
        assert info["private_key"] == "0xKey"
        mock_manager_class.assert_called_once_with(testnet=False)

    @patch('utils.account.AccountManager')
    def test_load_account(self, mock_manager_class):
        """Test load_account convenience function."""
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager

        manager = load_account("0xprivatekey", testnet=True)

        mock_manager_class.assert_called_once_with(private_key="0xprivatekey", testnet=True)


# ============================================================================
# Test Constants
# ============================================================================

class TestConstants:
    """Test module constants."""

    def test_chain_ids(self):
        """Test chain ID constants."""
        assert CHAIN_ID == 56
        assert TESTNET_CHAIN_ID == 97

    def test_rpc_urls(self):
        """Test RPC URL constants."""
        assert "binance" in MAINNET_RPC.lower()
        assert "binance" in TESTNET_RPC.lower()

    def test_token_addresses(self):
        """Test token address constants."""
        assert OPINION_USDT_ADDRESS.startswith("0x")
        assert len(OPINION_USDT_ADDRESS) == 42  # Ethereum address length

    def test_gas_limits(self):
        """Test gas limit constants."""
        assert DEFAULT_GAS_LIMIT > 0
        assert isinstance(DEFAULT_GAS_LIMIT, int)

    def test_decimals(self):
        """Test decimal constants."""
        assert USDT_DECIMALS == 18
        assert BNB_DECIMALS == 18


# ============================================================================
# Test Exceptions
# ============================================================================

class TestExceptions:
    """Test custom exception classes."""

    def test_account_error(self):
        """Test AccountError exception."""
        with pytest.raises(AccountError):
            raise AccountError("Test error")

    def test_insufficient_balance(self):
        """Test InsufficientBalance exception."""
        with pytest.raises(InsufficientBalance):
            raise InsufficientBalance("Not enough tokens")

    def test_insufficient_gas_balance(self):
        """Test InsufficientGasBalance exception."""
        with pytest.raises(InsufficientGasBalance):
            raise InsufficientGasBalance("Not enough BNB")

    def test_invalid_private_key(self):
        """Test InvalidPrivateKey exception."""
        with pytest.raises(InvalidPrivateKey):
            raise InvalidPrivateKey("Bad key")

    def test_transaction_failed(self):
        """Test TransactionFailed exception."""
        with pytest.raises(TransactionFailed):
            raise TransactionFailed("TX reverted")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
