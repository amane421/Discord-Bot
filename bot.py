import os
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import commands, tasks
from flask import Flask
import threading

# ========= Flask Keep Alive ========= #
app = Flask(__name__)

@app.route('/')
def home():
    return "I'm alive"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_flask).start()

# ========= Discord Bot ========= #
print("[STEP 1] import 開始")
print("[OK] os import 成功")
print("[OK] requests import 成功")
print("[OK] BeautifulSoup import 成功")
print("[OK] discord 関連 import 成功")

print("[STEP 2] 環境変数チェック")
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))
print(f"[OK] 環境変数取得成功 (CHANNEL_ID: {CHANNEL_ID})")

NITTER_MIRRORS = [
    "https://nitter.tiekoetter.com",
    "https://nitter.privacyredirect.com"
]

USERS = ["CryptoJPTrans", "angorou7"]
last_post_urls = {user: None for user in USERS}

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
print("[STEP 3] Bot 初期化")
print("[OK] Bot オブジェクト生成成功")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
}

def fetch_latest_post(user):
    for mirror in NITTER_MIRRORS:
        url = f"{mirror}/{user}"
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code != 200:
                print(f"[WARN] ステータスコード異常: {url} ({res.status_code})")
                continue
            soup = BeautifulSoup(res.text, "html.parser")
            article = soup.find("article") or \
                      soup.find("div", class_="timeline-item") or \
                      soup.find("div", class_="tweet")
            if not article:
                print(f"[WARN] 投稿が見つかりませんでした: {url}")
                continue

            post_link = article.find("a", href=True)
            if post_link and post_link['href'].startswith("/"):
                return mirror + post_link['href']
            else:
                print(f"[WARN] 投稿リンクが見つかりません: {url}")
        except Exception as e:
            print(f"[ERROR] {url} アクセス失敗: {e}")
    return None

@tasks.loop(minutes=10)
async def fetch_and_post():
    print("[TASK] fetch_and_post 実行開始")
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("[ERROR] チャンネル取得失敗")
        return
    print(f"[INFO] チャンネル取得成功: {channel.name}")

    for user in USERS:
        print(f"[CHECK] {user} の投稿チェック開始")
        latest_url = fetch_latest_post(user)
        if latest_url and latest_url != last_post_urls[user]:
            last_post_urls[user] = latest_url
            await channel.send(f"{user} の新着投稿: {latest_url}")
        else:
            print(f"[INFO] {user} の新規投稿なしまたは取得失敗")

@bot.event
async def on_ready():
    print("="*60)
    print(f"[READY] Bot logged in as {bot.user} (ID: {bot.user.id})")
    print("="*60)
    print("[STEP] 即時 fetch_and_post 実行")
    await fetch_and_post()
    print("[STEP] fetch_and_post.start() 実行")
    fetch_and_post.start()
    print("[STEP] fetch_and_post.start() 完了")

print("[STEP 4] bot.run() 実行開始")
bot.run(TOKEN)
