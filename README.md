# DexScreener Trading Bot

A powerful trading bot that scans tokens from the DexScreener API, applies strict filters, verifies safety, and sends trading signals via Telegram.

## ✨ Features

- 🔍 Fetch token profiles from [DexScreener](https://dexscreener.com) API.
- 🧹 Filter tokens based on:
  - Liquidity
  - Price range
  - Blacklisted coins and developers
- 🧠 Verify volume authenticity using:
  - Internal detection algorithm
  - [Pocket Universe](https://pocketuniverse.app) API
- 🛡️ Verify token safety using [RugCheck.xyz](https://rugcheck.xyz):
  - Only tokens marked as `"Good"`
  - Reject bundled tokens
- 🧾 Save token snapshots to a local SQLite database
- 📈 Analyze historical token data to detect pumps
- 📬 Send Telegram notifications (buy/sell signals) via [BonkBot](https://bonkbot.io)

---

## 🚀 Getting Started

### 1. Requirements

- Python 3.9 or later

### 2. Install dependencies

```bash
pip install requests sqlalchemy pandas python-telegram-bot
```

### 3. Create `config.json`

In the same directory as `dexscreener_bot.py`, create a `config.json` file with the following structure:

```json
{
  "filters": {
    "min_liquidity_usd": 10000,
    "min_price_usd": 0.0001,
    "max_price_usd": 10.0
  },
  "coin_blacklist": [
    "0xBadCoinAddress1",
    "0xBadCoinAddress2"
  ],
  "dev_blacklist": [
    "rug_dev1",
    "rug_dev2"
  ],
  "volume_verification": {
    "use_internal_algorithm": true,
    "fake_volume_threshold": 5.0,
    "use_pocket_universe": true,
    "pocket_universe": {
      "api_url": "https://api.pocketuniverse.com/verify",
      "api_token": "YOUR_POCKET_UNIVERSE_API_TOKEN"
    }
  },
  "rugcheck": {
    "required_status": "Good",
    "api_url": "https://api.rugcheck.xyz/verify",
    "api_token": "YOUR_RUGCHECK_API_TOKEN"
  },
  "telegram": {
    "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
    "chat_id": "YOUR_TELEGRAM_CHAT_ID"
  }
}
```

---

### 4. Run the bot

```bash
python dexscreener_bot.py
```

> 💡 For production use, consider running the script inside a `screen` or `tmux` session, or setting it up as a systemd service.

---

## 📄 License

MIT © YourNameHere