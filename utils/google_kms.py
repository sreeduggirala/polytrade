"""
Google Cloud KMS encryption for private keys.

This module provides encryption/decryption using Google Cloud Key Management Service
instead of local Fernet encryption. Keys are encrypted/decrypted by Google's HSMs.

Setup:
1. Enable Cloud KMS API: https://console.cloud.google.com/apis/library/cloudkms.googleapis.com
2. Create a key ring and key:
   gcloud kms keyrings create polymarket-bot --location=global
   gcloud kms keys create private-key-encryption \
       --location=global \
       --keyring=polymarket-bot \
       --purpose=encryption
3. Set environment variables:
   GOOGLE_CLOUD_PROJECT=your-project-id
   GCP_KMS_KEY_RING=polymarket-bot
   GCP_KMS_KEY_NAME=private-key-encryption
   GCP_KMS_LOCATION=global
4. Authenticate:
   - Local dev: gcloud auth application-default login
   - Production: Use service account with cloudkms.cryptoKeyEncrypterDecrypter role
"""

import os
import base64
import time
import logging
from typing import Optional
from functools import wraps
from google.cloud import kms
from google.api_core import retry, exceptions
from utils.kms_monitoring import get_monitor


class KMSEncryption:
    """Encrypt/decrypt data using Google Cloud KMS with rate limiting and retry logic."""

    # Rate limiting: Max operations per second
    MAX_OPS_PER_SECOND = 10
    _last_call_time = 0
    _call_count = 0

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        key_ring: Optional[str] = None,
        key_name: Optional[str] = None,
    ):
        """
        Initialize KMS encryption.

        Args:
            project_id: GCP project ID (defaults to GOOGLE_CLOUD_PROJECT env var)
            location: KMS location (defaults to GCP_KMS_LOCATION or 'global')
            key_ring: Key ring name (defaults to GCP_KMS_KEY_RING)
            key_name: Key name (defaults to GCP_KMS_KEY_NAME)
        """
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = location or os.getenv("GCP_KMS_LOCATION", "global")
        self.key_ring = key_ring or os.getenv("GCP_KMS_KEY_RING")
        self.key_name = key_name or os.getenv("GCP_KMS_KEY_NAME")

        # Validate required parameters
        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT not found in environment")
        if not self.key_ring:
            raise ValueError("GCP_KMS_KEY_RING not found in environment")
        if not self.key_name:
            raise ValueError("GCP_KMS_KEY_NAME not found in environment")

        # Handle credentials for Railway deployment
        # Railway can't use file paths, so we support JSON credentials in env var
        credentials_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        if credentials_json:
            import json
            import tempfile
            from google.oauth2 import service_account

            # Parse JSON credentials
            try:
                creds_dict = json.loads(credentials_json)
                credentials = service_account.Credentials.from_service_account_info(creds_dict)
                self.client = kms.KeyManagementServiceClient(credentials=credentials)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid GOOGLE_APPLICATION_CREDENTIALS_JSON: {e}")
        else:
            # Use default credentials (from GOOGLE_APPLICATION_CREDENTIALS file path)
            self.client = kms.KeyManagementServiceClient()

        # Build the key path
        self.key_path = self.client.crypto_key_path(
            self.project_id, self.location, self.key_ring, self.key_name
        )

        # Set up logging
        self.logger = logging.getLogger(__name__)

        # Set up monitoring
        self.monitor = get_monitor()

    def _rate_limit(self):
        """Rate limit KMS API calls to avoid hitting quotas."""
        current_time = time.time()

        # Reset counter every second
        if current_time - KMSEncryption._last_call_time >= 1.0:
            KMSEncryption._call_count = 0
            KMSEncryption._last_call_time = current_time

        # If we've hit the limit, sleep until next second
        if KMSEncryption._call_count >= self.MAX_OPS_PER_SECOND:
            sleep_time = 1.0 - (current_time - KMSEncryption._last_call_time)
            if sleep_time > 0:
                time.sleep(sleep_time)
            KMSEncryption._call_count = 0
            KMSEncryption._last_call_time = time.time()

        KMSEncryption._call_count += 1

    @retry.Retry(
        predicate=retry.if_exception_type(
            exceptions.ServiceUnavailable,
            exceptions.DeadlineExceeded,
            exceptions.InternalServerError,
        ),
        initial=1.0,
        maximum=10.0,
        multiplier=2.0,
        timeout=60.0,
    )
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt data using Google Cloud KMS with automatic retry on transient failures.

        Args:
            plaintext: The data to encrypt (e.g., private key)

        Returns:
            Base64-encoded encrypted data

        Raises:
            google.api_core.exceptions.GoogleAPIError: On KMS API errors
        """
        # Rate limit to avoid hitting quotas
        self._rate_limit()

        start_time = time.time()
        success = False

        try:
            # Convert string to bytes
            plaintext_bytes = plaintext.encode("utf-8")

            # Call KMS to encrypt
            encrypt_response = self.client.encrypt(
                request={"name": self.key_path, "plaintext": plaintext_bytes}
            )

            success = True

            # Return base64-encoded ciphertext for easy storage
            return base64.b64encode(encrypt_response.ciphertext).decode("utf-8")

        except Exception as e:
            self.logger.error(f"KMS encryption failed: {e}")
            raise

        finally:
            # Record metrics
            latency_ms = (time.time() - start_time) * 1000
            self.monitor.record_operation("encrypt", success, latency_ms)

    @retry.Retry(
        predicate=retry.if_exception_type(
            exceptions.ServiceUnavailable,
            exceptions.DeadlineExceeded,
            exceptions.InternalServerError,
        ),
        initial=1.0,
        maximum=10.0,
        multiplier=2.0,
        timeout=60.0,
    )
    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt data using Google Cloud KMS with automatic retry on transient failures.

        Args:
            ciphertext: Base64-encoded encrypted data

        Returns:
            Decrypted plaintext string

        Raises:
            google.api_core.exceptions.GoogleAPIError: On KMS API errors
        """
        # Rate limit to avoid hitting quotas
        self._rate_limit()

        start_time = time.time()
        success = False

        try:
            # Decode base64
            ciphertext_bytes = base64.b64decode(ciphertext.encode("utf-8"))

            # Call KMS to decrypt
            decrypt_response = self.client.decrypt(
                request={"name": self.key_path, "ciphertext": ciphertext_bytes}
            )

            success = True

            # Return decrypted string
            return decrypt_response.plaintext.decode("utf-8")

        except Exception as e:
            self.logger.error(f"KMS decryption failed: {e}")
            raise

        finally:
            # Record metrics
            latency_ms = (time.time() - start_time) * 1000
            self.monitor.record_operation("decrypt", success, latency_ms)


# Example usage
if __name__ == "__main__":
    # Test encryption/decryption
    kms = KMSEncryption()

    test_private_key = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"

    print("Testing Google Cloud KMS encryption...")
    encrypted = kms.encrypt(test_private_key)
    print(f"Encrypted: {encrypted[:50]}...")

    decrypted = kms.decrypt(encrypted)
    print(f"Decrypted: {decrypted}")

    assert decrypted == test_private_key
    print("✅ Encryption/decryption successful!")
