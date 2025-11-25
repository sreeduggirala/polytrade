"""
Simple monitoring/alerting for Google Cloud KMS operations.

Tracks:
- Total encrypt/decrypt calls
- Error rates
- Latency metrics
"""

import time
import logging
from typing import Dict
from collections import defaultdict


class KMSMonitor:
    """Monitor KMS operations and track metrics."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Metrics
        self.metrics: Dict[str, int] = defaultdict(int)
        self.latencies: Dict[str, list] = defaultdict(list)
        self.last_reset = time.time()

    def record_operation(self, operation: str, success: bool, latency_ms: float):
        """Record a KMS operation.

        Args:
            operation: 'encrypt' or 'decrypt'
            success: Whether operation succeeded
            latency_ms: Operation latency in milliseconds
        """
        # Increment counters
        self.metrics[f"{operation}_total"] += 1
        if success:
            self.metrics[f"{operation}_success"] += 1
        else:
            self.metrics[f"{operation}_error"] += 1

        # Track latency
        self.latencies[operation].append(latency_ms)

        # Alert on high error rate (>10%)
        total = self.metrics[f"{operation}_total"]
        errors = self.metrics[f"{operation}_error"]
        error_rate = (errors / total) * 100 if total > 0 else 0

        if total >= 10 and error_rate > 10:
            self.logger.warning(
                f"⚠️  High KMS {operation} error rate: {error_rate:.1f}% ({errors}/{total})"
            )

        # Alert on high latency (>1000ms average)
        if len(self.latencies[operation]) >= 10:
            avg_latency = sum(self.latencies[operation][-10:]) / 10
            if avg_latency > 1000:
                self.logger.warning(
                    f"⚠️  High KMS {operation} latency: {avg_latency:.0f}ms (avg of last 10)"
                )

    def get_stats(self) -> Dict[str, any]:
        """Get current statistics.

        Returns:
            Dictionary with operation counts, error rates, and latencies
        """
        stats = {}

        for operation in ['encrypt', 'decrypt']:
            total = self.metrics[f"{operation}_total"]
            errors = self.metrics[f"{operation}_error"]
            success = self.metrics[f"{operation}_success"]

            stats[operation] = {
                "total": total,
                "success": success,
                "errors": errors,
                "error_rate": (errors / total * 100) if total > 0 else 0,
            }

            # Latency stats
            if self.latencies[operation]:
                latencies = self.latencies[operation]
                stats[operation]["latency"] = {
                    "min": min(latencies),
                    "max": max(latencies),
                    "avg": sum(latencies) / len(latencies),
                    "count": len(latencies),
                }

        # Overall stats
        total_ops = self.metrics["encrypt_total"] + self.metrics["decrypt_total"]
        total_errors = self.metrics["encrypt_error"] + self.metrics["decrypt_error"]

        stats["overall"] = {
            "total_operations": total_ops,
            "total_errors": total_errors,
            "error_rate": (total_errors / total_ops * 100) if total_ops > 0 else 0,
            "uptime_seconds": time.time() - self.last_reset,
        }

        return stats

    def reset_stats(self):
        """Reset all statistics."""
        self.metrics.clear()
        self.latencies.clear()
        self.last_reset = time.time()
        self.logger.info("KMS monitoring stats reset")

    def log_stats(self):
        """Log current statistics."""
        stats = self.get_stats()

        self.logger.info("=== KMS Operation Statistics ===")
        self.logger.info(f"Total operations: {stats['overall']['total_operations']}")
        self.logger.info(f"Total errors: {stats['overall']['total_errors']}")
        self.logger.info(f"Overall error rate: {stats['overall']['error_rate']:.2f}%")

        for operation in ['encrypt', 'decrypt']:
            if operation in stats and stats[operation]['total'] > 0:
                op_stats = stats[operation]
                self.logger.info(f"\n{operation.capitalize()}:")
                self.logger.info(f"  Total: {op_stats['total']}")
                self.logger.info(f"  Success: {op_stats['success']}")
                self.logger.info(f"  Errors: {op_stats['errors']} ({op_stats['error_rate']:.1f}%)")

                if 'latency' in op_stats:
                    lat = op_stats['latency']
                    self.logger.info(f"  Latency: min={lat['min']:.0f}ms, avg={lat['avg']:.0f}ms, max={lat['max']:.0f}ms")


# Global monitor instance
_monitor_instance: KMSMonitor = None


def get_monitor() -> KMSMonitor:
    """Get the global KMS monitor instance."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = KMSMonitor()
    return _monitor_instance
