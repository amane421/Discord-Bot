import os
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands
from flask import Flask
import threading

# Flask アプリの作成（Renderのヘルスチェック用）
app = Flask(__name__)

@app.route("/")
def index():
    return "Bot is running"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# 環境変数からDiscord BotトークンとチャンネルIDを取得
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))

# 監視対象のNitterアカウントURL
NITTER_URLS = [
    "https://nitter.poast.org/CryptoJPTrans",
    "https://nitter.poast.org/angorou7"
]

# 各アカウントごとの最新投稿URL記録
last_post_urls = {}

# Discord Bot設定
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# 投稿取得・通知処理（60分おき）
@tasks.loop(minutes=60)
async def fetch_and_post():
    global last_post_urls
    for url in NITTER_URLS:
        try:
            response = requests.get(url, timeout=10, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            })
            if response.status_code != 200:
                print(f"[ERROR] Failed to fetch {url}: {response.status_code}")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            tweets = soup.select('.timeline-item')

            if not tweets:
                print(f"[INFO] No tweets found on {url}.")
                continue

            first = tweets[0]
            tweet_link_suffix = first.select_one('a.tweet-link')['href']
            tweet_url = f"https://twitter.com{tweet_link_suffix}"
            tweet_content = first.select_one('.tweet-content').text.strip()

            if url not in last_post_urls or tweet_url != last_post_urls[url]:
                last_post_urls[url] = tweet_url
                channel = bot.get_channel(CHANNEL_ID)
                if channel:
                    await channel.send(
                        f"✏️ [{url.split('/')[-1]}] 新しい投稿がありました！\n{tweet_content}\n{tweet_url}"
                    )
                    print(f"[INFO] New tweet posted from {url}")
                else:
                    print("[ERROR] Channel not found")
            else:
                print(f"[INFO] No new tweet for {url}.")

        except Exception as e:
            print(f"[EXCEPTION] Error fetching from {url}: {e}")

# Botログイン時に即時1回実行 → その後ループ開始
@bot.event
async def on_ready():
    print(f"[READY] Bot logged in as {bot.user}")
    await fetch_and_post()
    print("[INFO] fetch_and_post executed manually.")
    fetch_and_post.start()

# Flaskサーバー起動とBot起動を並列で実行
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(TOKEN)
