# Polytrade

![polymarket](https://github.com/user-attachments/assets/6d1edc58-7e89-4fe0-bb96-e1e843d9d0a1)





## Installation

### 1. Clone the repo
```
bash
git clone https://github.com/yourname/polytrade.git
cd polytrade
```

### 2. Install Dependencies
```
pip install -r requirements.txt
```

### 3. Setup environment variables
Copy `.env.example` to `.env` and configure:
```bash
# Polymarket Trading
PRIVATE_KEY=0xabc123...
POLYMARKET_PROXY_ADDRESS=0xdef456...
POLYMARKET_SIGNATURE_TYPE=1

# Telegram (for bot mode)
TELEGRAM_BOT_TOKEN=123456:ABCDEF-BOTTOKEN
```

### Copytrading Mode (Live Trading)
```
python main.py
```

- Tracks predefined wallets
- Places mirrored trades using best market price
- Sends Telegram alert on execution

Edit tracked wallets in `main.py`:
```python
TARGETS: Dict[str,str] = {  # wallet -> name
    "0x1234...": "tommy",
    "0x5678...": "shelby",
    # Add more...
}
```

# How It Works

### 1. Trade Polling

- Calls Polymarket’s public REST API every few seconds

- Sorts trades by (timestamp, txhash)

- Skips previously seen trades using in-memory `last_seen` cache

### 2. Order Execution

- Uses /price endpoint for best current price

- Places a FOK (fill-or-kill) order via py-clob-client

### 3. Notifications

- Telegram bot sends alerts using Markdown formatting

- Bot must be added to your channel and granted Post Messages permission

## Directory Structure
```
polytrade/
│
├── main.py                   # Main copytrading loop
├── bot.py                    # Telegram bot interface (multi-user)
├── polymarket.py             # Polymarket CLOB client wrapper
│
├── utils/
│   ├── polymarket_client.py  # Full Polymarket client implementation
│   ├── user_manager.py       # Multi-user wallet management
│   ├── account.py            # Polygon account utilities
│   ├── telegram.py           # Async Telegram helpers
│   ├── card.py               # Trading card generation
│   └── ...                   # Other utilities
│
├── .env                      # API keys and secrets
└── requirements.txt          # Python dependencies
```




