"""
Account Management for Polymarket Prediction Markets

Handles EOA (Externally Owned Account) operations using web3.py:
- Account creation and import
- Private key management and export
- Deposits and withdrawals
- Balance queries
- Transaction signing and sending

Integrates with Polymarket CLOB on Polygon (Chain ID: 137)
"""

import os
import json
from typing import Optional, Dict, Any, Tuple
from decimal import Decimal
from pathlib import Path
from eth_account import Account as EthAccount
from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.types import Wei, TxParams, HexStr
import secrets


# ============================================================================
# CONSTANTS
# ============================================================================

CHAIN_ID = 137  # Polygon mainnet
TESTNET_CHAIN_ID = 80002  # Polygon Amoy testnet

# Polygon RPC endpoints
MAINNET_RPC = "https://polygon-rpc.com/"
TESTNET_RPC = "https://rpc-amoy.polygon.technology/"

# Polymarket contract addresses on Polygon
POLYMARKET_USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC on Polygon
POLYMARKET_CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"  # CTF Exchange contract

# Gas limits
DEFAULT_GAS_LIMIT = 200000
APPROVAL_GAS_LIMIT = 100000

# Decimals
USDC_DECIMALS = 6  # USDC uses 6 decimals on Polygon
MATIC_DECIMALS = 18

# ERC20 ABI (minimal - just what we need)
ERC20_ABI = json.loads('''[
    {
        "constant": true,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": false,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": false,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": true,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": true,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]''')


# ============================================================================
# EXCEPTIONS
# ============================================================================

class AccountError(Exception):
    """Base exception for account operations."""
    pass


class InsufficientBalance(AccountError):
    """Insufficient balance for transaction."""
    pass


class InsufficientGasBalance(AccountError):
    """Insufficient MATIC for gas fees."""
    pass


class InvalidPrivateKey(AccountError):
    """Invalid private key format."""
    pass


class TransactionFailed(AccountError):
    """Transaction failed or reverted."""
    pass


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def to_wei(amount: float, decimals: int = 18) -> int:
    """
    Convert human-readable amount to wei.

    Args:
        amount: Amount in human-readable format
        decimals: Token decimals (default: 18)

    Returns:
        Amount in wei as integer
    """
    return int(Decimal(str(amount)) * Decimal(10 ** decimals))


def from_wei(amount: int, decimals: int = 18) -> float:
    """
    Convert wei to human-readable amount.

    Args:
        amount: Amount in wei
        decimals: Token decimals (default: 18)

    Returns:
        Human-readable amount as float
    """
    return float(Decimal(amount) / Decimal(10 ** decimals))


def format_address(address: str) -> str:
    """
    Format Ethereum address with checksum.

    Args:
        address: Ethereum address (with or without 0x prefix)

    Returns:
        Checksummed address
    """
    return Web3.to_checksum_address(address)


# ============================================================================
# ACCOUNT MANAGER
# ============================================================================

class AccountManager:
    """
    Manage EOA accounts for Polymarket prediction markets.

    Features:
    - Create new accounts or import existing ones
    - Manage private keys securely
    - Check balances (BNB and USDT)
    - Deposit/withdraw USDT
    - Approve spending for Polymarket contracts
    - Sign and send transactions
    """

    def __init__(
        self,
        private_key: Optional[str] = None,
        rpc_url: Optional[str] = None,
        testnet: bool = False,
    ):
        """
        Initialize account manager.

        Args:
            private_key: Private key (hex string with or without 0x)
            rpc_url: Custom RPC URL (overrides testnet setting)
            testnet: Use testnet instead of mainnet (default: False)
        """
        # Set up Web3 connection
        if rpc_url:
            self.rpc_url = rpc_url
        else:
            self.rpc_url = TESTNET_RPC if testnet else MAINNET_RPC

        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.testnet = testnet
        self.chain_id = TESTNET_CHAIN_ID if testnet else CHAIN_ID

        # Verify connection
        if not self.w3.is_connected():
            raise AccountError(f"Failed to connect to RPC: {self.rpc_url}")

        # Load or create account
        self.account: Optional[LocalAccount] = None
        if private_key:
            self.import_account(private_key)

    # ========================================================================
    # ACCOUNT CREATION & IMPORT
    # ========================================================================

    def create_account(self) -> Dict[str, str]:
        """
        Create a new EOA account.

        Returns:
            Dictionary with 'address' and 'private_key'

        Example:
            >>> manager = AccountManager()
            >>> account_info = manager.create_account()
            >>> print(account_info['address'])
            '0x1234...'
        """
        # Generate random private key
        private_key = "0x" + secrets.token_hex(32)

        # Create account from private key
        self.account = EthAccount.from_key(private_key)

        return {
            "address": self.account.address,
            "private_key": private_key,
        }

    def import_account(self, private_key: str) -> str:
        """
        Import an existing account from private key.

        Args:
            private_key: Private key (hex string with or without 0x prefix)

        Returns:
            Account address

        Raises:
            InvalidPrivateKey: If private key format is invalid

        Example:
            >>> manager = AccountManager()
            >>> address = manager.import_account("0xabc123...")
            >>> print(address)
            '0x1234...'
        """
        try:
            # Normalize private key format
            if not private_key.startswith("0x"):
                private_key = "0x" + private_key

            # Create account from private key
            self.account = EthAccount.from_key(private_key)

            return self.account.address

        except Exception as e:
            raise InvalidPrivateKey(f"Invalid private key format: {e}")

    def export_private_key(self) -> str:
        """
        Export the current account's private key.

        Returns:
            Private key as hex string with 0x prefix

        Raises:
            AccountError: If no account is loaded

        WARNING: Keep this private key secure! Anyone with access to it
        can control your funds.
        """
        if not self.account:
            raise AccountError("No account loaded. Create or import an account first.")

        return self.account.key.hex()

    def get_address(self) -> str:
        """
        Get the current account's address.

        Returns:
            Checksummed Ethereum address

        Raises:
            AccountError: If no account is loaded
        """
        if not self.account:
            raise AccountError("No account loaded. Create or import an account first.")

        return self.account.address

    # ========================================================================
    # BALANCE QUERIES
    # ========================================================================

    def get_matic_balance(self, address: Optional[str] = None) -> float:
        """
        Get MATIC balance for an address.

        Args:
            address: Address to check (uses loaded account if None)

        Returns:
            MATIC balance as float
        """
        if address is None:
            if not self.account:
                raise AccountError("No account loaded")
            address = self.account.address

        address = format_address(address)
        balance_wei = self.w3.eth.get_balance(address)
        return from_wei(balance_wei, MATIC_DECIMALS)

    def get_token_balance(
        self,
        token_address: str,
        address: Optional[str] = None,
    ) -> float:
        """
        Get ERC20 token balance for an address.

        Args:
            token_address: Token contract address
            address: Address to check (uses loaded account if None)

        Returns:
            Token balance as float
        """
        if address is None:
            if not self.account:
                raise AccountError("No account loaded")
            address = self.account.address

        address = format_address(address)
        token_address = format_address(token_address)

        # Create contract instance
        contract = self.w3.eth.contract(
            address=token_address,
            abi=ERC20_ABI
        )

        # Get balance and decimals
        balance_wei = contract.functions.balanceOf(address).call()
        decimals = contract.functions.decimals().call()

        return from_wei(balance_wei, decimals)

    def get_usdc_balance(self, address: Optional[str] = None) -> float:
        """
        Get USDC balance for an address.

        Args:
            address: Address to check (uses loaded account if None)

        Returns:
            USDC balance as float
        """
        return self.get_token_balance(POLYMARKET_USDC_ADDRESS, address)

    def get_all_balances(self, address: Optional[str] = None) -> Dict[str, float]:
        """
        Get all relevant balances for an address.

        Args:
            address: Address to check (uses loaded account if None)

        Returns:
            Dictionary with 'matic' and 'usdc' balances
        """
        return {
            "bnb": self.get_matic_balance(address),
            "usdt": self.get_usdc_balance(address),
        }

    # ========================================================================
    # TOKEN APPROVAL
    # ========================================================================

    def get_allowance(
        self,
        token_address: str,
        spender_address: str,
        owner_address: Optional[str] = None,
    ) -> float:
        """
        Check token allowance for a spender.

        Args:
            token_address: Token contract address
            spender_address: Spender contract address
            owner_address: Token owner address (uses loaded account if None)

        Returns:
            Approved amount as float
        """
        if owner_address is None:
            if not self.account:
                raise AccountError("No account loaded")
            owner_address = self.account.address

        owner_address = format_address(owner_address)
        token_address = format_address(token_address)
        spender_address = format_address(spender_address)

        contract = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)
        allowance_wei = contract.functions.allowance(
            owner_address,
            spender_address
        ).call()

        decimals = contract.functions.decimals().call()
        return from_wei(allowance_wei, decimals)

    def approve_token(
        self,
        token_address: str,
        spender_address: str,
        amount: Optional[float] = None,
        gas_price: Optional[int] = None,
    ) -> str:
        """
        Approve a spender to use tokens.

        Args:
            token_address: Token contract address
            spender_address: Spender contract address
            amount: Amount to approve (None = unlimited)
            gas_price: Custom gas price in wei (None = auto)

        Returns:
            Transaction hash

        Raises:
            AccountError: If no account is loaded
            InsufficientGasBalance: If insufficient MATIC for gas
            TransactionFailed: If transaction fails
        """
        if not self.account:
            raise AccountError("No account loaded")

        token_address = format_address(token_address)
        spender_address = format_address(spender_address)

        # Get token contract
        contract = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)
        decimals = contract.functions.decimals().call()

        # Set approval amount (max uint256 if None)
        if amount is None:
            amount_wei = 2**256 - 1  # Maximum uint256
        else:
            amount_wei = to_wei(amount, decimals)

        # Build transaction
        tx = contract.functions.approve(
            spender_address,
            amount_wei
        ).build_transaction({
            "from": self.account.address,
            "chainId": self.chain_id,
            "gas": APPROVAL_GAS_LIMIT,
            "gasPrice": gas_price or self.w3.eth.gas_price,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
        })

        # Check gas balance
        estimated_gas_cost = tx["gas"] * tx["gasPrice"]
        bnb_balance = self.w3.eth.get_balance(self.account.address)
        if bnb_balance < estimated_gas_cost:
            raise InsufficientGasBalance(
                f"Need {from_wei(estimated_gas_cost, MATIC_DECIMALS):.6f} MATIC for gas, "
                f"but only have {from_wei(bnb_balance, MATIC_DECIMALS):.6f} MATIC"
            )

        # Sign and send transaction
        signed_tx = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        return tx_hash.hex()

    def approve_usdc_for_polymarket(
        self,
        amount: Optional[float] = None,
    ) -> str:
        """
        Approve Polymarket router to spend USDT.

        Args:
            amount: Amount to approve (None = unlimited)

        Returns:
            Transaction hash
        """
        return self.approve_token(
            POLYMARKET_USDC_ADDRESS,
            POLYMARKET_CTF_EXCHANGE,
            amount
        )

    # ========================================================================
    # TRANSFERS (DEPOSITS & WITHDRAWALS)
    # ========================================================================

    def transfer_token(
        self,
        token_address: str,
        to_address: str,
        amount: float,
        gas_price: Optional[int] = None,
    ) -> str:
        """
        Transfer ERC20 tokens to another address.

        Args:
            token_address: Token contract address
            to_address: Recipient address
            amount: Amount to transfer
            gas_price: Custom gas price in wei (None = auto)

        Returns:
            Transaction hash

        Raises:
            AccountError: If no account is loaded
            InsufficientBalance: If insufficient token balance
            InsufficientGasBalance: If insufficient MATIC for gas
            TransactionFailed: If transaction fails
        """
        if not self.account:
            raise AccountError("No account loaded")

        token_address = format_address(token_address)
        to_address = format_address(to_address)

        # Get token contract
        contract = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)
        decimals = contract.functions.decimals().call()

        # Check balance
        balance_wei = contract.functions.balanceOf(self.account.address).call()
        amount_wei = to_wei(amount, decimals)

        if balance_wei < amount_wei:
            raise InsufficientBalance(
                f"Need {amount} tokens but only have {from_wei(balance_wei, decimals)}"
            )

        # Build transaction
        tx = contract.functions.transfer(
            to_address,
            amount_wei
        ).build_transaction({
            "from": self.account.address,
            "chainId": self.chain_id,
            "gas": DEFAULT_GAS_LIMIT,
            "gasPrice": gas_price or self.w3.eth.gas_price,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
        })

        # Check gas balance
        estimated_gas_cost = tx["gas"] * tx["gasPrice"]
        bnb_balance = self.w3.eth.get_balance(self.account.address)
        if bnb_balance < estimated_gas_cost:
            raise InsufficientGasBalance(
                f"Need {from_wei(estimated_gas_cost, MATIC_DECIMALS):.6f} MATIC for gas, "
                f"but only have {from_wei(bnb_balance, MATIC_DECIMALS):.6f} MATIC"
            )

        # Sign and send transaction
        signed_tx = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        return tx_hash.hex()

    def transfer_usdc(self, to_address: str, amount: float) -> str:
        """
        Transfer USDC to another address.

        Args:
            to_address: Recipient address
            amount: Amount in USDC

        Returns:
            Transaction hash
        """
        return self.transfer_token(POLYMARKET_USDC_ADDRESS, to_address, amount)

    def send_matic(self, to_address: str, amount: float) -> str:
        """
        Send MATIC to another address (wrapper for transfer_matic).

        Args:
            to_address: Recipient address
            amount: Amount in MATIC

        Returns:
            Transaction hash
        """
        return self.transfer_matic(to_address, amount)

    def send_usdc(self, to_address: str, amount: float) -> str:
        """
        Send USDC to another address (wrapper for transfer_usdc).

        Args:
            to_address: Recipient address
            amount: Amount in USDC

        Returns:
            Transaction hash
        """
        return self.transfer_usdc(to_address, amount)

    def transfer_matic(
        self,
        to_address: str,
        amount: float,
        gas_price: Optional[int] = None,
    ) -> str:
        """
        Transfer MATIC to another address.

        Args:
            to_address: Recipient address
            amount: Amount in MATIC
            gas_price: Custom gas price in wei (None = auto)

        Returns:
            Transaction hash

        Raises:
            AccountError: If no account is loaded
            InsufficientBalance: If insufficient MATIC
            TransactionFailed: If transaction fails
        """
        if not self.account:
            raise AccountError("No account loaded")

        to_address = format_address(to_address)
        amount_wei = to_wei(amount, MATIC_DECIMALS)

        # Check balance (need amount + gas)
        bnb_balance = self.w3.eth.get_balance(self.account.address)
        gas_price_wei = gas_price or self.w3.eth.gas_price
        estimated_gas_cost = 21000 * gas_price_wei  # Standard ETH transfer gas

        if bnb_balance < (amount_wei + estimated_gas_cost):
            raise InsufficientBalance(
                f"Need {from_wei(amount_wei + estimated_gas_cost, MATIC_DECIMALS):.6f} MATIC "
                f"(including gas) but only have {from_wei(bnb_balance, MATIC_DECIMALS):.6f} MATIC"
            )

        # Build transaction
        tx: TxParams = {
            "from": self.account.address,
            "to": to_address,
            "value": amount_wei,
            "chainId": self.chain_id,
            "gas": 21000,
            "gasPrice": gas_price_wei,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
        }

        # Sign and send transaction
        signed_tx = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        return tx_hash.hex()

    # ========================================================================
    # TRANSACTION UTILITIES
    # ========================================================================

    def wait_for_transaction(
        self,
        tx_hash: str,
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """
        Wait for a transaction to be confirmed.

        Args:
            tx_hash: Transaction hash to wait for
            timeout: Timeout in seconds (default: 120)

        Returns:
            Transaction receipt as dictionary

        Raises:
            TransactionFailed: If transaction fails or times out
        """
        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(
                tx_hash,
                timeout=timeout
            )

            # Check if transaction succeeded
            if receipt.get("status") == 0:
                raise TransactionFailed(f"Transaction {tx_hash} reverted")

            return dict(receipt)

        except Exception as e:
            raise TransactionFailed(f"Transaction failed: {e}")

    def get_transaction_status(self, tx_hash: str) -> Dict[str, Any]:
        """
        Get transaction status and details.

        Args:
            tx_hash: Transaction hash

        Returns:
            Dictionary with transaction info and status
        """
        try:
            # Try to get transaction receipt
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)

            return {
                "confirmed": True,
                "success": receipt.get("status") == 1,
                "block_number": receipt.get("blockNumber"),
                "gas_used": receipt.get("gasUsed"),
                "receipt": dict(receipt),
            }

        except TransactionNotFound:
            # Transaction not yet mined
            try:
                # Check if transaction exists in mempool
                tx = self.w3.eth.get_transaction(tx_hash)
                return {
                    "confirmed": False,
                    "pending": True,
                    "transaction": dict(tx),
                }
            except TransactionNotFound:
                return {
                    "confirmed": False,
                    "pending": False,
                    "error": "Transaction not found",
                }

    def estimate_gas(self, tx: TxParams) -> int:
        """
        Estimate gas for a transaction.

        Args:
            tx: Transaction parameters

        Returns:
            Estimated gas amount
        """
        return self.w3.eth.estimate_gas(tx)

    def get_gas_price(self) -> Dict[str, float]:
        """
        Get current gas price information.

        Returns:
            Dictionary with gas prices in gwei
        """
        gas_price_wei = self.w3.eth.gas_price

        return {
            "gas_price_wei": gas_price_wei,
            "gas_price_gwei": from_wei(gas_price_wei, 9),  # 1 gwei = 10^9 wei
        }

    # ========================================================================
    # CONVENIENCE METHODS
    # ========================================================================

    def deposit_usdc_to_polymarket(self, amount: float) -> Tuple[str, str]:
        """
        Convenience method to deposit USDC for Polymarket trading.

        This approves the Polymarket router to spend USDC and transfers
        USDC to the Polymarket platform.

        Args:
            amount: Amount in USDC to deposit

        Returns:
            Tuple of (approval_tx_hash, transfer_tx_hash)

        Note:
            In practice, Polymarket may use a different deposit mechanism
            (e.g., a deposit contract). Update this method accordingly.
        """
        # First, approve Polymarket router
        approval_tx = self.approve_usdc_for_polymarket(amount)
        self.wait_for_transaction(approval_tx)

        # Then transfer USDC (placeholder - update with actual Polymarket deposit method)
        # For now, this is just a token transfer
        transfer_tx = self.transfer_usdc(POLYMARKET_CTF_EXCHANGE, amount)

        return (approval_tx, transfer_tx)

    def withdraw_usdc_from_polymarket(
        self,
        amount: float,
        to_address: Optional[str] = None,
    ) -> str:
        """
        Convenience method to withdraw USDC from Polymarket trading.

        Args:
            amount: Amount in USDC to withdraw
            to_address: Destination address (uses loaded account if None)

        Returns:
            Transaction hash

        Note:
            In practice, Polymarket likely has a withdrawal contract method.
            Update this method accordingly.
        """
        if to_address is None:
            if not self.account:
                raise AccountError("No account loaded")
            to_address = self.account.address

        # Placeholder - update with actual Polymarket withdrawal method
        return self.transfer_usdc(to_address, amount)

    def __repr__(self) -> str:
        """String representation of AccountManager."""
        if self.account:
            return f"AccountManager(address={self.account.address}, chain_id={self.chain_id})"
        return f"AccountManager(no_account, chain_id={self.chain_id})"


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def create_new_account(testnet: bool = False) -> Tuple[AccountManager, Dict[str, str]]:
    """
    Create a new account and return both the manager and credentials.

    Args:
        testnet: Use testnet instead of mainnet

    Returns:
        Tuple of (AccountManager instance, account info dict)

    Example:
        >>> manager, info = create_new_account()
        >>> print(f"Address: {info['address']}")
        >>> print(f"Private key: {info['private_key']}")
    """
    manager = AccountManager(testnet=testnet)
    account_info = manager.create_account()
    return manager, account_info


def load_account(private_key: str, testnet: bool = False) -> AccountManager:
    """
    Load an existing account from private key.

    Args:
        private_key: Private key (with or without 0x prefix)
        testnet: Use testnet instead of mainnet

    Returns:
        AccountManager instance with loaded account

    Example:
        >>> manager = load_account("0xabc123...", testnet=False)
        >>> print(manager.get_address())
    """
    return AccountManager(private_key=private_key, testnet=testnet)


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

def main():
    """Example usage of AccountManager."""
    import sys

    print("=" * 60)
    print("ACCOUNT MANAGER - OPINION PREDICTION MARKETS")
    print("=" * 60)

    # Example 1: Create new account
    print("\n1. Creating new account...")
    manager, account_info = create_new_account(testnet=False)
    print(f"   Address: {account_info['address']}")
    print(f"   Private Key: {account_info['private_key'][:10]}...{account_info['private_key'][-10:]}")

    # Example 2: Check balances
    print("\n2. Checking balances...")
    balances = manager.get_all_balances()
    print(f"   MATIC: {balances['matic']:.6f}")
    print(f"   USDC: {balances['usdc']:.2f}")

    # Example 3: Import existing account (from env)
    print("\n3. Loading account from environment...")
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
    if private_key:
        manager2 = load_account(private_key, testnet=False)
        print(f"   Address: {manager2.get_address()}")
        balances2 = manager2.get_all_balances()
        print(f"   MATIC: {balances2['matic']:.6f}")
        print(f"   USDC: {balances2['usdc']:.2f}")
    else:
        print("   No POLYMARKET_PRIVATE_KEY found in environment")

    # Example 4: Gas price info
    print("\n4. Current gas prices...")
    gas_info = manager.get_gas_price()
    print(f"   Gas Price: {gas_info['gas_price_gwei']:.2f} gwei")

    print("\n" + "=" * 60)
    print("Available operations:")
    print("  - manager.create_account()")
    print("  - manager.import_account(private_key)")
    print("  - manager.get_matic_balance()")
    print("  - manager.get_usdc_balance()")
    print("  - manager.transfer_usdc(to_address, amount)")
    print("  - manager.transfer_matic(to_address, amount)")
    print("  - manager.approve_usdc_for_polymarket(amount)")
    print("  - manager.deposit_usdc_to_polymarket(amount)")
    print("  - manager.withdraw_usdc_from_polymarket(amount)")
    print("  - manager.export_private_key()")
    print("=" * 60)


if __name__ == "__main__":
    main()
