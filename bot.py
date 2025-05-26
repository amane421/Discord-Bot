import os
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands
from flask import Flask
import asyncio

# 環境変数からトークンとチャンネルIDを取得
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))

# Botインスタンスの作成
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Nitterインスタンスの候補リスト（信頼性の高いもの）
NITTER_INSTANCES = [
    "https://nitter.tiekoetter.com",
    "https://nitter.privacyredirect.com"
]

# 監視対象のアカウント
TARGET_ACCOUNTS = ["CryptoJPTrans", "angorou7"]

# 最新投稿URLの保存辞書
last_post_urls = {account: None for account in TARGET_ACCOUNTS}

# Flaskアプリ起動（Render用）
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running"

# 投稿取得関数
def fetch_latest_post(account):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    for base_url in NITTER_INSTANCES:
        url = f"{base_url}/{account}"
        try:
            res = requests.get(url, headers=headers, timeout=10)
     　　　   print(f"[DEBUG] {url} status_code: {res.status_code}")
     　　　   print(f"[DEBUG] {url} content preview: {res.text[:500]}")

            if res.status_code != 200:
                continue
            soup = BeautifulSoup(res.text, 'html.parser')
            a_tag = soup.select_one('a[href^="/' + account + '/status/"]')
            if a_tag:
                return base_url + a_tag['href']
        except Exception:
            continue
    return None

# 投稿チェックと送信
def check_new_post(account):
    latest_post = fetch_latest_post(account)
    if not latest_post:
        print(f"[INFO] {account} の新規投稿なしまたは取得失敗")
        return None
    if last_post_urls[account] != latest_post:
        last_post_urls[account] = latest_post
        return latest_post
    return None

# 投稿検知→Discord送信
def create_task():
    async def fetch_and_post():
        await bot.wait_until_ready()
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            print("[ERROR] Discordチャンネルが取得できませんでした")
            return

        for account in TARGET_ACCOUNTS:
            print(f"[CHECK] {account} の投稿チェック開始")
            latest_post = check_new_post(account)
            if latest_post:
                await channel.send(
                    f"🆕 {account} の新規投稿:\n{latest_post}"
                )

    return fetch_and_post

# 定期実行タスク
task_runner = tasks.loop(minutes=5)(create_task())

@bot.event
async def on_ready():
    print("=" * 60)
    print(f"[READY] Bot logged in as {bot.user} (ID: {bot.user.id})")
    print("=" * 60)
    await create_task()()
    task_runner.start()

if __name__ == '__main__':
    from threading import Thread

    print("[STEP 1] import 開始")
    print("[OK] os import 成功")
    print("[OK] requests import 成功")
    print("[OK] BeautifulSoup import 成功")
    print("[OK] discord 関連 import 成功")

    print("[STEP 2] 環境変数チェック")
    print(f"[OK] 環境変数取得成功 (CHANNEL_ID: {CHANNEL_ID})")

    print("[STEP 3] Bot 初期化")
    print("[OK] Bot オブジェクト生成成功")

    def run_flask():
        app.run(host="0.0.0.0", port=8080)

    t = Thread(target=run_flask)
    t.start()

    print("[STEP 4] bot.run() 実行開始")
    bot.run(TOKEN)
