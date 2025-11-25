-- PostgreSQL Schema for Polymarket Trading Bot
-- Database: PostgreSQL (direct connection via psycopg2)
-- Encryption: Google Cloud KMS (HSM-backed)

-- Create wallets table from scratch:
DROP TABLE IF EXISTS wallets;

CREATE TABLE wallets (
    id BIGSERIAL PRIMARY KEY,
    telegram_id TEXT UNIQUE NOT NULL,
    telegram_username TEXT,
    address TEXT NOT NULL,
    private_key TEXT NOT NULL,
    settings JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_wallets_telegram_id ON wallets(telegram_id);
CREATE INDEX idx_wallets_telegram_username ON wallets(telegram_username);
CREATE INDEX idx_wallets_address ON wallets(address);

-- Schema explanation:
-- id: Auto-increment primary key (BIGSERIAL)
-- telegram_id: Telegram user ID stored as TEXT - REQUIRED for bot lookups (UNIQUE)
-- telegram_username: @username (can be null if user has no username)
-- address: BNB Chain wallet address (TEXT)
-- private_key: Google Cloud KMS-encrypted private key (TEXT)
-- settings: User settings as JSONB (auto_reload, confirm_trades, etc.)
-- created_at: Account creation timestamp (TIMESTAMPTZ)

COMMENT ON TABLE wallets IS 'Multi-user wallet storage with KMS encryption';
COMMENT ON COLUMN wallets.telegram_id IS 'Telegram user ID (stored as string) - used for lookups';
COMMENT ON COLUMN wallets.telegram_username IS 'Telegram @username (optional)';
COMMENT ON COLUMN wallets.address IS 'BNB Chain wallet address';
COMMENT ON COLUMN wallets.private_key IS 'Google Cloud KMS-encrypted private key (HSM-backed)';
COMMENT ON COLUMN wallets.settings IS 'User preferences stored as JSONB';
