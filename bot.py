import os
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands
from flask import Flask
import threading

# Flask アプリの作成
app = Flask(__name__)

@app.route("/")
def index():
    return "Bot is running"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# 環境変数からトークンとチャンネルIDを取得
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))

# NitterアカウントのURLリスト
NITTER_URLS = [
    "https://nitter.poast.org/CryptoJPTrans",
    "https://nitter.poast.org/angorou7"
]

# 最新投稿の保存用
last_post_urls = {}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@tasks.loop(minutes=60)
async def fetch_and_post():
    global last_post_urls
    for url in NITTER_URLS:
        try:
            response = requests.get(url, timeout=10, headers={
                "User-Agent": "Mozilla/5.0"
            })
            if response.status_code != 200:
                print(f"[ERROR] Failed to fetch {url}: {response.status_code}")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            tweets = soup.select('.timeline-item')

            if not tweets:
                print(f"[INFO] No tweets found on {url}")
                continue

            first = tweets[0]
            tweet_link_suffix = first.select_one('a.tweet-link')['href']
            tweet_url = f"https://twitter.com{tweet_link_suffix}"
            tweet_content = first.select_one('.tweet-content').text.strip()

            if url not in last_post_urls or tweet_url != last_post_urls[url]:
                last_post_urls[url] = tweet_url
                channel = await bot.fetch_channel(CHANNEL_ID)  # ← ここ修正
                if channel:
                    await channel.send(f"✏️ [{url.split('/')[-1]}] 新しい投稿がありました！\n{tweet_content}\n{tweet_url}")
                    print(f"[POSTED] {url} -> {tweet_url}")
                else:
                    print(f"[ERROR] Channel not found (ID: {CHANNEL_ID})")
            else:
                print(f"[SKIPPED] No new tweet for {url}")

        except Exception as e:
            print(f"[EXCEPTION] ({url}) {e}")

@bot.event
async def on_ready():
    print(f"[READY] Bot logged in as {bot.user}")
    try:
        await fetch_and_post()
        print("[INFO] fetch_and_post executed manually.")
    except Exception as e:
        print(f"[ERROR] fetch_and_post failed: {e}")
    fetch_and_post.start()

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(TOKEN)
