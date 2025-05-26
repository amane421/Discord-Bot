import os
import discord
from discord.ext import commands, tasks
from flask import Flask
import requests
from bs4 import BeautifulSoup
import asyncio

# Flaskサーバーの起動（Render用）
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running!"

# トークンの取得
TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
CHANNEL_ID = int(os.environ.get('DISCORD_CHANNEL_ID'))

# Intentsの設定
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True  # ←これがないとメッセージ取得できない
intents.guilds = True

# Botの定義
bot = commands.Bot(command_prefix='!', intents=intents)

# ニュース取得関数
def get_crypto_news():
    print("[DEBUG] get_crypto_news() called")  # ← ログ追加

    url = 'https://coinpost.jp/'
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Failed to fetch news: {e}")
        return "ニュースの取得に失敗しました。"

    soup = BeautifulSoup(response.content, 'html.parser')
    news_items = soup.select('.articleList .catLabel + a')[:3]

    if not news_items:
        print("[WARNING] No news items found on the page.")
        return "最新のニュースが見つかりませんでした。"

    news_list = ["【最新ニュース】"]
    for item in news_items:
        title = item.text.strip()
        link = item.get('href')
        if link and not link.startswith("http"):
            link = "https://coinpost.jp" + link
        news_list.append(f"{title}\n{link}")

    result = "\n\n".join(news_list)
    print(f"[DEBUG] News scraped:\n{result}")
    return result

# ニュースを定期投稿するタスク
@tasks.loop(minutes=60)
async def fetch_and_post():
    print("[DEBUG] fetch_and_post() called")  # ← タスク起動確認
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if channel is None:
            print(f"[ERROR] Channel ID {CHANNEL_ID} not found.")
            return
        news = get_crypto_news()
        await channel.send(news)
        print("[INFO] News posted successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to fetch and post news: {e}")

# Bot起動時の処理
@bot.event
async def on_ready():
    try:
        print(f"[READY] Logged in as {bot.user}")  # ← ログイン確認
    except Exception as e:
        print(f"[CRITICAL] failed to print READY: {e}")

    try:
        print("[DEBUG] Calling fetch_and_post() manually")
        await fetch_and_post()
        print("[INFO] fetch_and_post() executed manually")
    except Exception as e:
        print(f"[ERROR] fetch_and_post() failed on startup: {e}")

    try:
        fetch_and_post.start()
        print("[INFO] fetch_and_post() loop started")
    except Exception as e:
        print(f"[ERROR] fetch_and_post.start() failed: {e}")

# FlaskとDiscordの同時実行
async def run_bot():
    loop = asyncio.get_event_loop()
    loop.create_task(bot.start(TOKEN))
    app.run(host="0.0.0.0", port=8080)

if __name__ == '__main__':
    try:
        asyncio.run(run_bot())
    except Exception as e:
        print(f"[CRITICAL] Failed to start bot: {e}")
