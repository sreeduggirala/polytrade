#!/usr/bin/env python3
"""
Database Migration Script
Run this to apply referral_schema.sql to your production database.

Usage:
    python3 migrate_database.py
"""

import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_migration():
    """Apply referral_schema.sql migration to database."""
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("❌ ERROR: DATABASE_URL not found in environment variables")
        print("Make sure your .env file contains DATABASE_URL")
        return False

    print(f"🔗 Connecting to database...")

    try:
        # Connect to database
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        print("✅ Connected successfully")
        print("📖 Reading migration file...")

        # Read SQL migration file
        with open("referral_schema.sql", "r") as f:
            sql_commands = f.read()

        print("🚀 Executing migration...")

        # Execute migration
        cursor.execute(sql_commands)
        conn.commit()

        print("✅ Migration completed successfully!")
        print("\n📊 Checking tables...")

        # Verify tables exist
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('wallets', 'points_history')
            ORDER BY table_name
        """)

        tables = cursor.fetchall()
        print(f"\n✓ Found tables: {', '.join([t[0] for t in tables])}")

        # Check wallets columns
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'wallets'
            AND column_name IN ('referral_code', 'referred_by', 'total_points', 'total_volume')
            ORDER BY column_name
        """)

        columns = cursor.fetchall()
        print(f"✓ Referral columns in wallets: {', '.join([c[0] for c in columns])}")

        cursor.close()
        conn.close()

        print("\n🎉 Database migration completed successfully!")
        print("You can now use /points and /referral commands")

        return True

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print("\nTroubleshooting:")
        print("1. Check DATABASE_URL is correct in .env")
        print("2. Make sure you have network access to the database")
        print("3. Verify database user has CREATE TABLE permissions")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("    Database Migration - Referral System")
    print("=" * 60)
    print()

    success = run_migration()

    print()
    print("=" * 60)

    exit(0 if success else 1)
