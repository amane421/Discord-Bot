import os
import requests
import traceback
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands
from flask import Flask

# ==== 初期化ログ ====
print("[STEP 1] import 開始")
print("[OK] os import 成功")
print("[OK] requests import 成功")
print("[OK] BeautifulSoup import 成功")
print("[OK] discord 関連 import 成功")

# ==== 環境変数 ====
print("[STEP 2] 環境変数チェック")
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))
print(f"[OK] 環境変数取得成功 (CHANNEL_ID: {CHANNEL_ID})")

# ==== Bot 初期化 ====
print("[STEP 3] Bot 初期化")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
print("[OK] Bot オブジェクト生成成功")

# ==== Nitterミラーと対象アカウント ====
NITTER_MIRRORS = [
    "https://nitter.tiekoetter.com",
    "https://nitter.privacyredirect.com"
]
TARGET_USERS = ["CryptoJPTrans", "angorou7"]
last_post_urls = {}

# ==== 投稿取得＆送信 ====
@tasks.loop(minutes=10)
async def fetch_and_post():
    print("[TASK] fetch_and_post 実行開始")
    try:
        channel = bot.get_channel(CHANNEL_ID)
        print(f"[INFO] チャンネル取得成功: {channel.name}")

        for user in TARGET_USERS:
            posted = False
            for mirror in NITTER_MIRRORS:
                url = f"{mirror}/{user}"
                print(f"[CHECK] {url} の投稿チェック開始")

                try:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                    }
                    response = requests.get(url, headers=headers, timeout=10)
                    if response.status_code != 200:
                        print(f"[WARN] ステータスコード異常: {url} ({response.status_code})")
                        continue

                    soup = BeautifulSoup(response.text, "html.parser")
                    article = soup.find("article")
                    if not article:
                        print(f"[WARN] 投稿が見つかりませんでした: {url}")
                        continue

                    # 記事リンクを抽出
                    post_path = article.find("a", href=True)
                    if not post_path:
                        print(f"[WARN] 投稿リンクが見つかりません: {url}")
                        continue

                    full_url = mirror + post_path['href']
                    if last_post_urls.get(user) != full_url:
                        await channel.send(f"🆕 新着投稿 from `{user}`\n{full_url}")
                        last_post_urls[user] = full_url
                        print(f"[POST] 新規投稿送信: {full_url}")
                    else:
                        print(f"[SKIP] 既に投稿済み: {full_url}")
                    posted = True
                    break  # ミラー成功 → 他はスキップ

                except Exception as e:
                    print(f"[ERROR] {url} アクセス失敗: {e}")
                    traceback.print_exc()
            if not posted:
                print(f"[INFO] {user} の新規投稿なしまたは取得失敗")

    except Exception as e:
        print(f"[ERROR] fetch_and_post 全体でエラー: {e}")
        traceback.print_exc()

# ==== 起動時処理 ====
@bot.event
async def on_ready():
    print("============================================================")
    print(f"[READY] Bot logged in as {bot.user} (ID: {bot.user.id})")
    print("============================================================")
    print("[STEP] 即時 fetch_and_post 実行")
    await fetch_and_post()
    print("[STEP] fetch_and_post.start() 実行")
    fetch_and_post.start()
    print("[STEP] fetch_and_post.start() 完了")

# ==== FlaskによるRender用サーバー起動 ====
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running."

if __name__ == "__main__":
    print("[STEP 4] bot.run() 実行開始")
    bot.run(TOKEN)
