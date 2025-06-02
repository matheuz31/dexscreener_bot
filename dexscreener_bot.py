#!/usr/bin/env python3
"""
DexScreener Trading Bot

Features:
  - Fetch token profiles from DexScreener API.
  - Filter tokens based on liquidity, price, coin blacklist, developer blacklist.
  - Verify volume authenticity via an internal algorithm and the Pocket Universe API.
  - Verify token safety using RugCheck.xyz (only accept tokens marked as "Good" and not bundled).
  - Save token snapshots to a SQLite database.
  - Analyze historical data for "pumped" tokens and send Telegram notifications (buy/sell signals) via BonkBot.

Instructions to launch:
1. Install Python 3.9+.
2. Install required packages:
     pip install requests sqlalchemy pandas python-telegram-bot
3. Create a config.json file in the same directory with contents similar to:

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

4. Run the script:
     python dexscreener_bot.py

For production, consider running it inside a screen/tmux session or as a service.
"""

import requests
import logging
import json
import time
import datetime
import pandas as pd
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, JSON
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from telegram import Bot
import asyncio

# ---------------------------
# Config Loader
# ---------------------------
def load_config(config_path="config.json"):
    with open(config_path, "r") as f:
        config = json.load(f)
    return config

# ---------------------------
# DexScreener API Client Module
# ---------------------------
class DexscreenerClient:
    BASE_URL = "https://api.dexscreener.com"

    def __init__(self):
        self.session = requests.Session()
        self.logger = logging.getLogger(__name__)
    
    def get_latest_token_profiles(self):
        url = f"{self.BASE_URL}/token-profiles/latest/v1"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
    
    def get_latest_boosted_tokens(self):
        url = f"{self.BASE_URL}/token-boosts/latest/v1"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
    
    def get_top_boosted_tokens(self):
        url = f"{self.BASE_URL}/token-boosts/top/v1"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
    
    def search_pairs(self, query):
        url = f"{self.BASE_URL}/latest/dex/search"
        params = {"q": query}
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def get_token_info(self, chain_id: str, token_address: str):
        url = f"{self.BASE_URL}/tokens/v1/{chain_id}/{token_address}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

# ---------------------------
# Volume Verification Helper
# ---------------------------
def verify_volume(token_data, config):
    """
    Verify whether the token's reported volume is genuine.
    Uses an internal algorithm and/or the Pocket Universe API.
    """
    vol_ver_config = config.get("volume_verification", {})
    fake_threshold = vol_ver_config.get("fake_volume_threshold", 5.0)
    
    try:
        current_volume = float(token_data.get('volume', {}).get('h1', 0))
    except (TypeError, ValueError):
        current_volume = 0
    
    print("current", current_volume)

    if vol_ver_config.get("use_internal_algorithm", False):
        if current_volume < fake_threshold:
            logging.info(f"Internal volume check: {current_volume} < {fake_threshold}")
            return False
        else:
            logging.info(f"Internal volume check passed: {current_volume} >= {fake_threshold}")
    
    if vol_ver_config.get("use_pocket_universe", False):
        pu_config = vol_ver_config.get("pocket_universe", {})
        api_url = pu_config.get("api_url")
        api_token = pu_config.get("api_token")
        if api_url and api_token:
            try:
                payload = {"tokenAddress": token_data.get("tokenAddress")}
                headers = {"Authorization": f"Bearer {api_token}"}
                response = requests.post(api_url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
                if not result.get("volumeAuthentic", False):
                    logging.info(f"Pocket Universe API flagged token {token_data.get('tokenAddress')}.")
                    return False
            except Exception as e:
                logging.error(f"Pocket Universe API error for token {token_data.get('tokenAddress')}: {e}")
                return False
    return True

# ---------------------------
# RugCheck Verification Helper
# ---------------------------
def verify_rugcheck(token_data, config):
    """
    Verify the token using RugCheck.xyz.
    Checks that the token's status is the required value (e.g., "Good")
    and that its supply is not bundled.
    """
    rugcheck_conf = config.get("rugcheck", {})
    required_status = rugcheck_conf.get("required_status", "Good")
    api_url = rugcheck_conf.get("api_url")
    api_token = rugcheck_conf.get("api_token")
    token_addr = token_data.get("tokenAddress")
    if not api_url or not api_token or not token_addr:
        logging.warning("RugCheck config incomplete or token address missing; skipping rugcheck.")
        return False

    try:
        payload = {"tokenAddress": token_addr}
        headers = {"Authorization": f"Bearer {api_token}"}
        response = requests.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        status = result.get("status", "")
        bundled = result.get("bundled", False)
        logging.info(f"RugCheck for {token_addr}: status={status}, bundled={bundled}")
        if status != required_status:
            logging.info(f"Token {token_addr} rejected (status: {status}).")
            return False
        if bundled:
            logging.info(f"Token {token_addr} rejected due to bundled supply.")
            return False
    except Exception as e:
        logging.error(f"RugCheck error for token {token_addr}: {e}")
        return False

    return True

# ---------------------------
# Telegram Notification Helper
# ---------------------------
async def send_telegram_notification(message, config):
    """
    Sends a message via Telegram using BonkBot.
    Requires 'telegram' section in the config with 'bot_token' and 'chat_id'.
    """
    telegram_conf = config.get("telegram", {})
    bot_token = telegram_conf.get("bot_token")
    chat_id = telegram_conf.get("chat_id")
    if not bot_token or not chat_id:
        logging.warning("Telegram configuration missing; cannot send notification.")
        return
    try:
        bot = Bot(token=bot_token)
        async with bot:
            await bot.send_message(chat_id=chat_id, text=message)
            logging.info("Telegram notification sent.")
    except Exception as e:
        logging.error(f"Error sending Telegram notification: {e}")

# ---------------------------
# Data Storage Module using SQLAlchemy
# ---------------------------
Base = declarative_base()

class TokenSnapshot(Base):
    __tablename__ = 'token_snapshots'
    id = Column(Integer, primary_key=True)
    token_address = Column(String, index=True)
    chain_id = Column(String)
    icon = Column(String)
    description = Column(String)
    links = Column(JSON)
    price_usd = Column(Float)
    liquidity = Column(Float)
    volume_usd = Column(Float)
    developer = Column(String)  # Optional field
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

engine = create_engine('sqlite:///dexscreener_data.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# ---------------------------
# Analysis Module
# ---------------------------
def analyze_token_trends(session, config):
    query = session.query(TokenSnapshot)
    data = [{
        'token_address': snap.token_address,
        'price_usd': snap.price_usd,
        'liquidity': snap.liquidity,
        'volume_usd': snap.volume_usd,
        'timestamp': snap.timestamp
    } for snap in query.all()]
    
    df = pd.DataFrame(data)
    if df.empty:
        return []
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp')
    
    flagged = []
    for token, group in df.groupby('token_address'):
        group = group.set_index('timestamp')
        hourly = group['price_usd'].resample('1h').last().dropna()
        if len(hourly) < 2:
            continue
        change = (hourly.iloc[-1] - hourly.iloc[0]) / hourly.iloc[0] * 100
        if change > 50:
            flagged.append((token, change))
    
    return flagged

# ---------------------------
# Main Scheduler Loop
# ---------------------------
def main_loop():
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    coin_blacklist = config.get("coin_blacklist", [])
    dev_blacklist = config.get("dev_blacklist", [])
    filters = config.get("filters", {})

    client = DexscreenerClient()
    session_db = Session()
    
    while True:
        try:
            profiles = client.get_latest_token_profiles()
            # Verifica se 'profiles' é dict ou lista
            if isinstance(profiles, dict):
                token_list = profiles.get('data', [])
            elif isinstance(profiles, list):
                token_list = profiles
            else:
                token_list = []
            
            for token_data in token_list:
                token_addr = token_data.get('tokenAddress')
                print(token_data)
                if token_addr in coin_blacklist:
                    logging.info(f"Skipping blacklisted coin: {token_addr}")
                    continue

                dev = token_data.get('developer')
                if dev and (dev.lower() in [d.lower() for d in dev_blacklist]):
                    logging.info(f"Skipping token by blacklisted developer: {dev}")
                    continue
                
                token_adress = token_data.get("tokenAddress")
                chain_id = token_data.get("chainId")

                info = client.get_token_info(chain_id, token_adress)[0]

                # print("pools", info)

                try:
                    liquidity = float(info.get('liquidity', {}).get('usd', 0))
                except (TypeError, ValueError):
                    liquidity = 0
                try:
                    price_usd = float(info.get('priceUsd', 0))
                except (TypeError, ValueError):
                    price_usd = 0

                if liquidity < filters.get("min_liquidity_usd", 0):
                    logging.info(f"Token {token_addr} skipped: low liquidity {liquidity}.")
                    continue

                if not (filters.get("min_price_usd", 0) <= price_usd <= filters.get("max_price_usd", float('inf'))):
                    logging.info(f"Token {token_addr} skipped: price {price_usd} out of range.")
                    continue

                if not verify_volume(info, config):
                    logging.info(f"Token {token_addr} skipped: suspicious volume.")
                    continue

                if not verify_rugcheck(token_data, config):
                    logging.info(f"Token {token_addr} skipped: rugcheck failed.")

                try:
                    volume_usd = float(info.get('volume', {}).get('h1', 0))
                except (TypeError, ValueError):
                    volume_usd = 0

                snapshot = TokenSnapshot(
                    token_address=token_addr,
                    chain_id=token_data.get('chainId'),
                    icon=token_data.get('icon'),
                    description=token_data.get('description'),
                    links=token_data.get('links'),
                    price_usd=price_usd,
                    liquidity=liquidity,
                    volume_usd=volume_usd,
                    developer=token_data.get('developer')
                )
                session_db.add(snapshot)
            
            session_db.commit()
            logging.info("Data fetched and stored successfully.")
            
            flagged_tokens = analyze_token_trends(session_db, config)
            if flagged_tokens:
                for token, pct in flagged_tokens:
                    msg = f"BUY SIGNAL: Token {token} is pumped by {pct:.2f}% in the last hour!"
                    logging.info(msg)
                    asyncio.run(send_telegram_notification(msg, config))
            else:
                logging.info("No tokens flagged in this analysis cycle.")
            
        except Exception as e:
            logging.error(f"Error during main loop: {e}")
            session_db.rollback()
        
        # Run every 10 minutes (adjust as necessary)
        time.sleep(600)

if __name__ == "__main__":
    main_loop()
