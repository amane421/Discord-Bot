import os
import traceback
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands
from flask import Flask

TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))

USER_AGENT = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}

NITTER_MIRRORS = [
    "https://nitter.tiekoetter.com",
    "https://nitter.privacyredirect.com"
]

ACCOUNTS = [
    "CryptoJPTrans",
    "angorou7"
]

last_post_urls = {}

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running."

def fetch_latest_post(account):
    for base_url in NITTER_MIRRORS:
        try:
            url = f"{base_url}/{account}"
            response = requests.get(url, headers=USER_AGENT, timeout=10)

            if response.status_code != 200:
                print(f"[WARN] ステータスコード異常: {url} ({response.status_code})")
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            article = soup.find("article")
            if not article:
                print(f"[WARN] 投稿が見つかりませんでした: {url}")
                continue

            a_tag = article.find("a", href=True)
            if a_tag and a_tag["href"]:
                post_url = base_url + a_tag["href"]
                return post_url

        except Exception as e:
            print(f"[ERROR] {url} アクセス失敗: {e}")

    return None

@bot.event
async def on_ready():
    print("=" * 60)
    print(f"[READY] Bot logged in as {bot.user} (ID: {bot.user.id})")
    print("=" * 60)
    print("[STEP] 即時 fetch_and_post 実行")
    await fetch_and_post()
    fetch_and_post.start()

@tasks.loop(minutes=10)
async def fetch_and_post():
    try:
        print("[TASK] fetch_and_post 実行開始")
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            print("[ERROR] チャンネル取得失敗")
            return
        print(f"[INFO] チャンネル取得成功: {channel.name}")

        for account in ACCOUNTS:
            print(f"[CHECK] {account} の投稿チェック開始")
            latest_post = fetch_latest_post(account)

            if not latest_post:
                print(f"[INFO] {account} の新規投稿なしまたは取得失敗")
                continue

            if last_post_urls.get(account) == latest_post:
                print(f"[INFO] {account} に新規投稿なし")
                continue

            last_post_urls[account] = latest_post
            await channel.send(f"🆕 {account} の新規投稿:\n{title}\n{url}")
{latest_post}")

    except Exception:
        traceback.print_exc()

if __name__ == "__main__":
    print("[STEP 1] import 開始")
    print("[OK] os import 成功")
    print("[OK] requests import 成功")
    print("[OK] BeautifulSoup import 成功")
    print("[OK] discord 関連 import 成功")

    print("[STEP 2] 環境変数チェック")
    print(f"[OK] 環境変数取得成功 (CHANNEL_ID: {CHANNEL_ID})")

    print("[STEP 3] Bot 初期化")
    print("[OK] Bot オブジェクト生成成功")

    print("[STEP 4] bot.run() 実行開始")
    bot.run(TOKEN)
