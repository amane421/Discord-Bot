import os
import sys
import traceback
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands

print("[BOOT] Bot 起動準備開始")

# === 環境変数の取得と検証 ===
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID_STR = os.environ.get("DISCORD_CHANNEL_ID")

try:
    if not TOKEN:
        raise ValueError("環境変数 DISCORD_TOKEN が未設定です")

    if not CHANNEL_ID_STR or not CHANNEL_ID_STR.isdigit():
        raise ValueError(f"DISCORD_CHANNEL_ID の値が不正です: {CHANNEL_ID_STR}")

    CHANNEL_ID = int(CHANNEL_ID_STR)
    print(f"[BOOT] 環境変数ロード成功 (CHANNEL_ID: {CHANNEL_ID})")

except Exception as e:
    print(f"[ERROR] 起動前チェックエラー: {e}")
    sys.exit(1)

# === Nitter URLと履歴 ===
NITTER_URLS = [
    "https://nitter.poast.org/CryptoJPTrans",
    "https://nitter.poast.org/angorou7"
]
last_post_urls = {}

# === Bot 初期化 ===
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@tasks.loop(minutes=60)
async def fetch_and_post():
    print("[TASK] fetch_and_post 実行開始")

    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            print(f"[ERROR] チャンネルID {CHANNEL_ID} が見つかりません（botが参加していない可能性あり）")
            return
        print(f"[INFO] チャンネル取得成功: {channel.name}")
    except Exception as e:
        print(f"[EXCEPTION] チャンネル取得エラー: {e}")
        return

    for url in NITTER_URLS:
        print(f"[CHECK] {url} の投稿チェック開始")
        try:
            response = requests.get(url, timeout=10)
            print(f"[DEBUG] HTTP ステータス: {response.status_code}")

            if response.status_code != 200:
                print(f"[WARN] {url} は取得できませんでした")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            tweets = soup.select('.timeline-item')
            if not tweets:
                print(f"[INFO] {url}: .timeline-item が見つかりませんでした")
                continue

            first = tweets[0]
            link = first.select_one('a.tweet-link')
            content = first.select_one('.tweet-content')

            if not link or not content:
                print(f"[WARN] {url}: 必要な要素が見つかりません（link: {link}, content: {content}）")
                continue

            tweet_url = f"https://twitter.com{link['href']}"
            tweet_text = content.text.strip()
            user = url.split('/')[-1]

            if tweet_url != last_post_urls.get(url):
                print(f"[NEW] 新規投稿: {tweet_url}")
                last_post_urls[url] = tweet_url
                await channel.send(f"📝 [{user}] 新しい投稿がありました！\n{tweet_text}\n{tweet_url}")
            else:
                print(f"[INFO] {url}: 既に記録済みの投稿です")

        except Exception as e:
            print(f"[EXCEPTION] 投稿チェック中の例外: {e}")
            traceback.print_exc()

# === Bot 起動後イベント ===
@bot.event
async def on_ready():
    print("=" * 60)
    print(f"[READY] on_ready() 呼び出し開始")
    print(f"[READY] Bot logged in as {bot.user} (ID: {bot.user.id})")
    print("=" * 60)

    try:
        print("[STEP] fetch_and_post() を即時実行")
        await fetch_and_post()
        print("[STEP] fetch_and_post() 実行完了")

        print("[STEP] fetch_and_post.start() を実行")
        fetch_and_post.start()
        print("[STEP] fetch_and_post.start() 完了")
    except Exception as e:
        print(f"[ERROR] on_ready() 内でエラー発生: {e}")
        traceback.print_exc()

# === Bot 起動実行 ===
try:
    print("[BOOT] bot.run() 実行開始")
    bot.run(TOKEN)
except Exception as e:
    print(f"[EXCEPTION] bot.run() 実行失敗: {e}")
    traceback.print_exc()
