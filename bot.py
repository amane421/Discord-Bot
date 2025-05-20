import os
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands
from keep_alive import keep_alive  # ← Replit常時稼働用

# 環境変数からトークンとチャンネルIDを取得
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))

# 対象NitterアカウントのURLリスト
NITTER_URLS = [
    "https://nitter.poast.org/CryptoJPTrans",
    "https://nitter.poast.org/angorou7"
]

# 各アカウントごとの最新投稿URLを記録
last_post_urls = {}

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@tasks.loop(minutes=60)  # ← 1時間おきにチェック
async def fetch_and_post():
    global last_post_urls
    for url in NITTER_URLS:
        try:
            response = requests.get(url, timeout=10)
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

            # 新規投稿があれば通知
            if url not in last_post_urls or tweet_url != last_post_urls[url]:
                last_post_urls[url] = tweet_url
                channel = bot.get_channel(CHANNEL_ID)
                if channel:
                    await channel.send(f"📝 [{url.split('/')[-1]}] 新しい投稿がありました！\n{tweet_content}\n{tweet_url}")
                else:
                    print("[ERROR] Channel not found")
            else:
                print(f"[INFO] No new tweet for {url}.")

        except Exception as e:
            print(f"[EXCEPTION] ({url}) {e}")

@bot.event
async def on_ready():
    print(f"[READY] Bot logged in as {bot.user}")
    fetch_and_post.start()

# ReplitのPing維持
keep_alive()

# 起動
bot.run(TOKEN)
