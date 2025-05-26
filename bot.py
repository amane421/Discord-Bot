import os
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands

# 環境変数取得
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID"))

# URLと履歴
NITTER_URLS = [
    "https://nitter.poast.org/CryptoJPTrans",
    "https://nitter.poast.org/angorou7"
]
last_post_urls = {}

# Botセットアップ
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@tasks.loop(minutes=60)
async def fetch_and_post():
    print("[TASK] fetch_and_post 実行開始")

    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            print(f"[ERROR] チャンネルID {CHANNEL_ID} が見つかりません")
            return
        print(f"[INFO] チャンネル取得成功: {channel.name}")
    except Exception as e:
        print(f"[EXCEPTION] チャンネル取得エラー: {e}")
        return

    for url in NITTER_URLS:
        print(f"[CHECK] {url} の投稿チェック開始")
        try:
            response = requests.get(url, timeout=10)
            print(f"[DEBUG] HTTPステータス: {response.status_code}")
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            tweets = soup.select('.timeline-item')
            if not tweets:
                print(f"[INFO] {url}: ツイートが見つかりませんでした")
                continue

            first = tweets[0]
            link = first.select_one('a.tweet-link')
            content = first.select_one('.tweet-content')

            if not link or not content:
                print(f"[WARN] {url}: 必要な要素が見つかりません")
                continue

            tweet_url = f"https://twitter.com{link['href']}"
            tweet_text = content.text.strip()
            user = url.split('/')[-1]

            if tweet_url != last_post_urls.get(url):
                print(f"[NEW] 新規投稿: {tweet_url}")
                last_post_urls[url] = tweet_url
                await channel.send(f"📝 [{user}] 新しい投稿がありました！\n{tweet_text}\n{tweet_url}")
            else:
                print(f"[INFO] {url}: 新しい投稿はありません")
        except Exception as e:
            print(f"[EXCEPTION] {url}: {e}")

@bot.event
async def on_ready():
    print("=" * 50)
    print(f"[READY] Bot logged in as {bot.user}")
    print("=" * 50)

    try:
        print("[INFO] 即時fetch_and_post 実行")
        await fetch_and_post()
        fetch_and_post.start()
        print("[INFO] fetch_and_post ループ開始")
    except Exception as e:
        print(f"[EXCEPTION] on_ready 内エラー: {e}")

# Bot起動
try:
    bot.run(TOKEN)
except Exception as e:
    print(f"[EXCEPTION] bot.run 失敗: {e}")
