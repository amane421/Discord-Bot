import os
import sys
import traceback
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands
from flask import Flask
import threading

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
    print("[ERROR] DISCORD_TOKEN or CHANNEL_ID が環境変数に設定されていません")
    sys.exit(1)

print(f"[OK] 環境変数取得成功 (CHANNEL_ID: {CHANNEL_ID})")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36"
}

NITTER_INSTANCES = [
    "https://nitter.tiekoetter.com",
    "https://nitter.privacyredirect.com",
    "https://lightbrd.com",
    "https://nitter.net",
    "https://nitter.poast.org"
]

TARGET_USERS = ["CryptoJPTrans", "angorou7"]
last_post_urls = {}

intents = discord.Intents.default()
intents.message_content = True

print("[STEP 3] Bot 初期化")
bot = commands.Bot(command_prefix="!", intents=intents)
print("[OK] Bot オブジェクト生成成功")

@bot.event
async def on_ready():
    print("="*60)
    print(f"[READY] Bot logged in as {bot.user} (ID: {bot.user.id})")
    print("="*60)
    print("[STEP] 即時 fetch_and_post 実行")
    await fetch_and_post()
    fetch_and_post.start()


def fetch_latest_post(user):
    for base_url in NITTER_INSTANCES:
        try:
            url = f"{base_url}/{user}"
            print(f"[CHECK] {url} の投稿チェック開始")
            response = requests.get(url, headers=HEADERS, timeout=10)
            print(f"[DEBUG] ステータスコード: {response.status_code}")
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                article = soup.find("a", {"class": "tweet-link"})
                if not article:
                    article = soup.find("a", href=lambda x: x and f"/{user}/status" in x)
                if article:
                    return f"{base_url}{article.get('href')}"
                else:
                    print(f"[WARN] 投稿が見つかりませんでした: {url}")
            else:
                print(f"[WARN] ステータスコード異常: {url} ({response.status_code})")
        except Exception as e:
            print(f"[ERROR] {url} アクセス失敗: {e}")
    return None


@tasks.loop(minutes=5)
async def fetch_and_post():
    print("[TASK] fetch_and_post 実行開始")
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print("[ERROR] 指定チャンネルが見つかりません")
        return
    print(f"[INFO] チャンネル取得成功: {channel.name}")

    for user in TARGET_USERS:
        latest_post_url = fetch_latest_post(user)
        if latest_post_url and latest_post_url != last_post_urls.get(user):
            await channel.send(f"{user} の新規投稿です\n{latest_post_url}")
            last_post_urls[user] = latest_post_url
        else:
            print(f"[INFO] {user} の新規投稿なしまたは取得失敗")

print("[STEP 4] bot.run() 実行開始")

app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running."

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = threading.Thread(target=run)
    t.start()

keep_alive()
bot.run(TOKEN)
