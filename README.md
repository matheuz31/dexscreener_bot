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
