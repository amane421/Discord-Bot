import os
import sys
import traceback
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands
from keep_alive import keep_alive  # Replit等を使っている場合のみ

print("[STEP 1] import 開始")
print("[OK] os import 成功")
print("[OK] sys, traceback import 成功")
print("[OK] requests import 成功")
print("[OK] BeautifulSoup import 成功")
print("[OK] discord 関連 import 成功")

print("[STEP 2] 環境変数チェック")
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))

if not TOKEN or not CHANNEL_ID:
    print("[ERROR] 環境変数が設定されていません")
    sys.exit(1)

print(f"[OK] 環境変数取得成功 (CHANNEL_ID: {CHANNEL_ID})")

print("[STEP 3] Bot 初期化")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
print("[OK] Bot オブジェクト生成成功")

# 複数のNitterミラー
NITTER_INSTANCES = [
    "https://nitter.tiekoetter.com",
    "https://nitter.privacyredirect.com",
    "https://lightbrd.com",
]

TARGET_USERS = [
    "CryptoJPTrans",
    "angorou7"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

last_post_urls = {}

def fetch_latest_post(user):
    for base_url in NITTER_INSTANCES:
        try:
            url = f"{base_url}/{user}"
            print(f"[CHECK] {url} の投稿チェック開始")
            response = requests.get(url, headers=HEADERS, timeout=10)
            print(f"[DEBUG] ステータスコード: {response.status_code}")
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                
                # 投稿リンク候補1: 古い形式
                article = soup.find("a", {"class": "tweet-link"})
                
                # 投稿リンク候補2: hrefに"/<user>/status"が含まれている最初のaタグ
                if not article:
                    article = soup.find("a", href=lambda x: x and f"/{user}/status" in x)

                if article:
                    return f"{base_url}{article.get('href')}"
                else:
                    print(f"[WARN] 投稿が見つかりませんでした: {url}")
            else:
                print(f"[WARN] {url} ステータスコード異常: {response.status_code}")
        except Exception as e:
            print(f"[ERROR] {base_url} へのアクセス失敗: {e}")
    return None

@bot.event
async def on_ready():
    print("=" * 60)
    print(f"[READY] Bot logged in as {bot.user} (ID: {bot.user.id})")
    print("=" * 60)
    print("[STEP] 即時 fetch_and_post 実行")
    await fetch_and_post()
    print("[STEP] fetch_and_post.start() 実行")
    fetch_and_post.start()
    print("[STEP] fetch_and_post.start() 完了")

@tasks.loop(minutes=5)
async def fetch_and_post():
    print("[TASK] fetch_and_post 実行開始")
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print("[ERROR] チャンネルが見つかりません")
        return

    print(f"[INFO] チャンネル取得成功: {channel.name}")
    for user in TARGET_USERS:
        post_url = fetch_latest_post(user)
        if post_url and last_post_urls.get(user) != post_url:
            last_post_urls[user] = post_url
            await channel.send(f"🆕 新しい投稿があります: {post_url}")
            print(f"[INFO] 投稿通知済み: {post_url}")
        else:
            print(f"[INFO] {user} の新規投稿なしまたは取得失敗")

print("[STEP 4] bot.run() 実行開始")
keep_alive()  # 必要に応じてコメントアウト
bot.run(TOKEN)
