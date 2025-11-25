"""
Copytrading Module - Multi-user Wallet Tracking & Trade Mirroring

Allows users to subscribe to wallets and automatically mirror their trades.
Designed for integration with multi-user Telegram bot.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable, Any
from pathlib import Path

from loguru import logger

from utils.polymarket_client import PolymarketClient, Trade


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class CopySubscription:
    """A user's subscription to copy a wallet."""
    user_id: int  # Telegram user ID
    target_wallet: str  # Wallet to copy
    target_name: str  # Friendly name for the wallet
    scale_factor: float = 1.0  # Trade scale (0.25 = 25% of original)
    enabled: bool = True
    created_at: int = field(default_factory=lambda: int(time.time()))

    # Cursor tracking
    last_seen_ts: int = 0
    last_seen_tx: str = ""
    last_seen_li: int = 0

    @property
    def cursor(self) -> Tuple[int, str, int]:
        return (self.last_seen_ts, self.last_seen_tx, self.last_seen_li)

    def update_cursor(self, trade: Trade) -> None:
        """Update cursor from a trade."""
        self.last_seen_ts = trade.timestamp
        self.last_seen_tx = trade.tx_hash
        self.last_seen_li = 0  # Data API doesn't provide log_index

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for storage."""
        return {
            "user_id": self.user_id,
            "target_wallet": self.target_wallet,
            "target_name": self.target_name,
            "scale_factor": self.scale_factor,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_seen_ts": self.last_seen_ts,
            "last_seen_tx": self.last_seen_tx,
            "last_seen_li": self.last_seen_li,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CopySubscription":
        """Deserialize from dict."""
        return cls(
            user_id=data["user_id"],
            target_wallet=data["target_wallet"],
            target_name=data["target_name"],
            scale_factor=data.get("scale_factor", 1.0),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", 0),
            last_seen_ts=data.get("last_seen_ts", 0),
            last_seen_tx=data.get("last_seen_tx", ""),
            last_seen_li=data.get("last_seen_li", 0),
        )


@dataclass
class MirrorResult:
    """Result of a mirror operation."""
    success: bool
    trade: Trade
    subscription: CopySubscription
    error: Optional[str] = None
    executed_amount: float = 0.0


# ============================================================================
# COPYTRADING MANAGER
# ============================================================================

class CopytradingManager:
    """
    Manages copytrading subscriptions for all users.

    Features:
    - Per-user wallet subscriptions
    - Configurable scale factors
    - Cursor-based deduplication
    - Background polling
    """

    def __init__(
        self,
        get_user_client: Callable[[int], Optional[PolymarketClient]],
        on_mirror_complete: Optional[Callable[[MirrorResult], Any]] = None,
        storage_path: str = "copytrading_subs.json",
    ):
        """
        Initialize copytrading manager.

        Args:
            get_user_client: Function to get PolymarketClient for a user ID
            on_mirror_complete: Callback when a trade is mirrored (for notifications)
            storage_path: Path to persist subscriptions
        """
        self.get_user_client = get_user_client
        self.on_mirror_complete = on_mirror_complete
        self.storage_path = Path(storage_path)

        # Subscriptions: {user_id: {wallet_address: CopySubscription}}
        self.subscriptions: Dict[int, Dict[str, CopySubscription]] = {}

        # Load persisted subscriptions
        self._load_subscriptions()

        # Polling state
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None

    # ========================================================================
    # SUBSCRIPTION MANAGEMENT
    # ========================================================================

    def subscribe(
        self,
        user_id: int,
        wallet: str,
        name: str,
        scale_factor: float = 1.0,
    ) -> CopySubscription:
        """
        Subscribe a user to copy a wallet.

        Args:
            user_id: Telegram user ID
            wallet: Wallet address to copy
            name: Friendly name for the wallet
            scale_factor: Trade scale (0.25 = 25%)

        Returns:
            The created subscription
        """
        wallet = wallet.lower()

        if user_id not in self.subscriptions:
            self.subscriptions[user_id] = {}

        sub = CopySubscription(
            user_id=user_id,
            target_wallet=wallet,
            target_name=name,
            scale_factor=scale_factor,
        )

        self.subscriptions[user_id][wallet] = sub
        self._save_subscriptions()

        logger.info(f"User {user_id} subscribed to {name} ({wallet[:10]}...) @ {scale_factor*100:.0f}%")
        return sub

    def unsubscribe(self, user_id: int, wallet: str) -> bool:
        """
        Unsubscribe a user from a wallet.

        Returns:
            True if subscription existed and was removed
        """
        wallet = wallet.lower()

        if user_id not in self.subscriptions:
            return False

        if wallet not in self.subscriptions[user_id]:
            return False

        del self.subscriptions[user_id][wallet]
        if not self.subscriptions[user_id]:
            del self.subscriptions[user_id]

        self._save_subscriptions()
        logger.info(f"User {user_id} unsubscribed from {wallet[:10]}...")
        return True

    def get_user_subscriptions(self, user_id: int) -> List[CopySubscription]:
        """Get all subscriptions for a user."""
        if user_id not in self.subscriptions:
            return []
        return list(self.subscriptions[user_id].values())

    def set_subscription_enabled(
        self,
        user_id: int,
        wallet: str,
        enabled: bool,
    ) -> bool:
        """Enable or disable a subscription."""
        wallet = wallet.lower()

        if user_id not in self.subscriptions:
            return False
        if wallet not in self.subscriptions[user_id]:
            return False

        self.subscriptions[user_id][wallet].enabled = enabled
        self._save_subscriptions()
        return True

    def update_scale_factor(
        self,
        user_id: int,
        wallet: str,
        scale_factor: float,
    ) -> bool:
        """Update scale factor for a subscription."""
        wallet = wallet.lower()

        if user_id not in self.subscriptions:
            return False
        if wallet not in self.subscriptions[user_id]:
            return False

        self.subscriptions[user_id][wallet].scale_factor = scale_factor
        self._save_subscriptions()
        return True

    # ========================================================================
    # POLLING & MIRRORING
    # ========================================================================

    async def start_polling(self, interval_sec: float = 2.0):
        """Start background polling for all subscriptions."""
        if self._running:
            logger.warning("Polling already running")
            return

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop(interval_sec))
        logger.info(f"Copytrading polling started (interval={interval_sec}s)")

    async def stop_polling(self):
        """Stop background polling."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("Copytrading polling stopped")

    async def _poll_loop(self, interval: float):
        """Main polling loop."""
        while self._running:
            try:
                await self._poll_all_subscriptions()
            except Exception as e:
                logger.exception(f"Error in poll loop: {e}")

            await asyncio.sleep(interval)

    async def _poll_all_subscriptions(self):
        """Poll all active subscriptions for new trades."""
        # Group subscriptions by target wallet to avoid duplicate API calls
        wallet_to_subs: Dict[str, List[CopySubscription]] = {}

        for user_subs in self.subscriptions.values():
            for sub in user_subs.values():
                if not sub.enabled:
                    continue
                if sub.target_wallet not in wallet_to_subs:
                    wallet_to_subs[sub.target_wallet] = []
                wallet_to_subs[sub.target_wallet].append(sub)

        # Fetch trades for each unique wallet
        for wallet, subs in wallet_to_subs.items():
            try:
                trades = PolymarketClient.fetch_wallet_trades(wallet, limit=50)
                if not trades:
                    continue

                # Process trades for each subscription
                for sub in subs:
                    await self._process_trades_for_subscription(sub, trades)

            except Exception as e:
                logger.error(f"Error polling wallet {wallet[:10]}...: {e}")

    async def _process_trades_for_subscription(
        self,
        sub: CopySubscription,
        trades: List[Trade],
    ):
        """Process trades for a single subscription."""
        # Find new trades (newer than cursor)
        new_trades = []
        for trade in trades:
            if self._is_newer(trade, sub.cursor):
                new_trades.append(trade)

        if not new_trades:
            return

        # Process oldest first (trades are returned newest-first)
        new_trades.reverse()

        for trade in new_trades:
            result = await self._mirror_trade(sub, trade)

            if result.success:
                # Update cursor only on success
                sub.update_cursor(trade)
                self._save_subscriptions()

            # Notify callback
            if self.on_mirror_complete:
                try:
                    await self.on_mirror_complete(result)
                except Exception as e:
                    logger.error(f"Error in mirror callback: {e}")

    async def _mirror_trade(
        self,
        sub: CopySubscription,
        trade: Trade,
    ) -> MirrorResult:
        """Mirror a single trade for a subscription."""
        client = self.get_user_client(sub.user_id)
        if not client:
            return MirrorResult(
                success=False,
                trade=trade,
                subscription=sub,
                error="User client not available",
            )

        try:
            # Calculate scaled amount
            scaled_value = trade.value * sub.scale_factor

            if scaled_value < 1.0:
                # Skip tiny trades
                logger.debug(f"Skipping trade below $1: ${scaled_value:.2f}")
                return MirrorResult(
                    success=True,  # Mark as success to advance cursor
                    trade=trade,
                    subscription=sub,
                    error="Skipped (below minimum)",
                    executed_amount=0,
                )

            # Execute trade
            if trade.is_buy:
                result = client.buy(trade.token_id, scaled_value)
            else:
                result = client.sell(trade.token_id, amount_usdc=scaled_value)

            logger.info(
                f"Mirrored {trade.side} for user {sub.user_id}: "
                f"${scaled_value:.2f} on {trade.token_id[:10]}..."
            )

            return MirrorResult(
                success=True,
                trade=trade,
                subscription=sub,
                executed_amount=scaled_value,
            )

        except Exception as e:
            logger.error(f"Failed to mirror trade for user {sub.user_id}: {e}")
            return MirrorResult(
                success=False,
                trade=trade,
                subscription=sub,
                error=str(e),
            )

    def _is_newer(self, trade: Trade, cursor: Tuple[int, str, int]) -> bool:
        """Check if a trade is newer than cursor."""
        cursor_ts, cursor_tx, cursor_li = cursor

        if trade.timestamp != cursor_ts:
            return trade.timestamp > cursor_ts

        if trade.tx_hash != cursor_tx:
            return trade.tx_hash > cursor_tx

        return False

    # ========================================================================
    # PERSISTENCE
    # ========================================================================

    def _save_subscriptions(self):
        """Save subscriptions to disk."""
        try:
            data = {}
            for user_id, user_subs in self.subscriptions.items():
                data[str(user_id)] = {
                    wallet: sub.to_dict()
                    for wallet, sub in user_subs.items()
                }

            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save subscriptions: {e}")

    def _load_subscriptions(self):
        """Load subscriptions from disk."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)

            for user_id_str, user_subs in data.items():
                user_id = int(user_id_str)
                self.subscriptions[user_id] = {}
                for wallet, sub_data in user_subs.items():
                    self.subscriptions[user_id][wallet] = CopySubscription.from_dict(sub_data)

            total = sum(len(s) for s in self.subscriptions.values())
            logger.info(f"Loaded {total} copytrading subscriptions")

        except Exception as e:
            logger.error(f"Failed to load subscriptions: {e}")


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_manager: Optional[CopytradingManager] = None


def get_copytrading_manager() -> Optional[CopytradingManager]:
    """Get the global copytrading manager."""
    return _manager


def init_copytrading_manager(
    get_user_client: Callable[[int], Optional[PolymarketClient]],
    on_mirror_complete: Optional[Callable[[MirrorResult], Any]] = None,
    storage_path: str = "copytrading_subs.json",
) -> CopytradingManager:
    """Initialize the global copytrading manager."""
    global _manager
    _manager = CopytradingManager(
        get_user_client=get_user_client,
        on_mirror_complete=on_mirror_complete,
        storage_path=storage_path,
    )
    return _manager
