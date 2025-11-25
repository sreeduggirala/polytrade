#!/usr/bin/env python3
"""
Quick test script to verify Supabase connection and schema.
Run this after setting up .env with SUPABASE_URL and SUPABASE_KEY.
"""

import os
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
load_dotenv()

def test_supabase():
    """Test Supabase connection and schema."""

    # Get credentials
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        print("❌ Missing SUPABASE_URL or SUPABASE_KEY in .env")
        return False

    print(f"✅ Found credentials")
    print(f"   URL: {url}")
    print(f"   Key: {key[:20]}...")

    # Create client
    try:
        supabase = create_client(url, key)
        print("✅ Supabase client created")
    except Exception as e:
        print(f"❌ Failed to create client: {e}")
        return False

    # Test connection by querying users table
    try:
        result = supabase.table("users").select("*").limit(1).execute()
        print("✅ Successfully connected to users table")
        print(f"   Found {len(result.data)} rows (limited to 1)")

        if result.data:
            print(f"   Sample row columns: {list(result.data[0].keys())}")

            # Check for telegram_id column
            if 'telegram_id' in result.data[0]:
                print("✅ telegram_id column exists")
                # Check if it's stored correctly
                sample_id = result.data[0].get('telegram_id')
                if sample_id:
                    print(f"   Sample telegram_id: {sample_id} (type: {type(sample_id).__name__})")
            else:
                print("⚠️  telegram_id column NOT FOUND")
                print("   Run this SQL in Supabase:")
                print("   ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_id TEXT UNIQUE;")
                print("   CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);")
        else:
            print("   Table is empty (this is OK for new setup)")

    except Exception as e:
        print(f"❌ Failed to query users table: {e}")
        print("   Make sure the 'users' table exists in your Supabase project")
        return False

    # Test encryption key
    encryption_key = os.getenv("STORAGE_ENCRYPTION_KEY")
    if encryption_key:
        print("✅ STORAGE_ENCRYPTION_KEY found")
        try:
            from cryptography.fernet import Fernet
            cipher = Fernet(encryption_key.encode())
            test_encrypted = cipher.encrypt(b"test")
            test_decrypted = cipher.decrypt(test_encrypted)
            print("✅ Encryption/decryption working")
        except Exception as e:
            print(f"❌ Invalid encryption key: {e}")
            print("   Generate new key with:")
            print("   python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
            return False
    else:
        print("⚠️  STORAGE_ENCRYPTION_KEY not found in .env")
        print("   Generate one with:")
        print("   python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")

    print("\n" + "="*60)
    print("✅ Supabase setup looks good!")
    print("="*60)
    return True

if __name__ == "__main__":
    test_supabase()
