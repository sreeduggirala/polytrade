-- Referral and Points System Schema
-- Adds referral codes and points tracking to the Polymarket Trading Bot

-- Add referral columns to wallets table
ALTER TABLE wallets
ADD COLUMN IF NOT EXISTS referral_code TEXT UNIQUE,
ADD COLUMN IF NOT EXISTS referred_by TEXT REFERENCES wallets(referral_code),
ADD COLUMN IF NOT EXISTS total_points DECIMAL(20, 2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_volume DECIMAL(20, 2) DEFAULT 0;

-- Create index for referral lookups
CREATE INDEX IF NOT EXISTS idx_wallets_referral_code ON wallets(referral_code);
CREATE INDEX IF NOT EXISTS idx_wallets_referred_by ON wallets(referred_by);

-- Create points_history table for detailed tracking
CREATE TABLE IF NOT EXISTS points_history (
    id BIGSERIAL PRIMARY KEY,
    telegram_id TEXT NOT NULL REFERENCES wallets(telegram_id),
    points_earned DECIMAL(20, 2) NOT NULL,
    points_type TEXT NOT NULL,  -- 'trade', 'referral_trade', 'referral_signup'
    volume DECIMAL(20, 2),
    market_id INT,
    market_title TEXT,
    referred_user_id TEXT,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_points_history_telegram_id ON points_history(telegram_id);
CREATE INDEX IF NOT EXISTS idx_points_history_created_at ON points_history(created_at);
CREATE INDEX IF NOT EXISTS idx_points_history_points_type ON points_history(points_type);

-- Schema explanation:
-- wallets.referral_code: Unique 7-character alphanumeric code (auto-generated, customizable)
-- wallets.referred_by: Referral code of the user who referred this user
-- wallets.total_points: Total points earned (1 point per $1 volume + referral bonuses)
-- wallets.total_volume: Total trading volume in USDT
--
-- points_history.points_type:
--   'trade' - Points from user's own trades (1 point per $1)
--   'referral_trade' - Points from referred user's trades (0.1 point per $1 their volume)
--   'referral_signup' - Bonus points for new referral (100 points)
--
-- Points earning structure:
-- - Own trades: 1 point per $1 volume
-- - Referral signup: 100 points bonus
-- - Referral's trades: 10% of their points (0.1 point per $1 their volume)

COMMENT ON COLUMN wallets.referral_code IS 'Unique 7-char alphanumeric referral code';
COMMENT ON COLUMN wallets.referred_by IS 'Referral code of referring user';
COMMENT ON COLUMN wallets.total_points IS 'Total points earned (volume + referrals)';
COMMENT ON COLUMN wallets.total_volume IS 'Total trading volume in USDT';
COMMENT ON TABLE points_history IS 'Detailed points earning history';
