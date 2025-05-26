# =========================
# import チェックセクション
# =========================
print("[STEP 1] import 開始")

try:
    import os
    print("[OK] os import 成功")
    import sys
    import traceback
    print("[OK] sys, traceback import 成功")
    import requests
    print("[OK] requests import 成功")
    from bs4 import BeautifulSoup
    print("[OK] BeautifulSoup import 成功")
    import discord
    from discord.ext import tasks, commands
    print("[OK] discord 関連 import 成功")
except Exception as e:
    print("[ERROR] import 中に例外発生:")
    traceback.print_exc()
    sys.exit(1)

# =========================
# 環境変数チェック
# =========================
print("[STEP 2] 環境変数チェック")

try:
    TOKEN = os.environ.get("DISCORD_TOKEN")
    CHANNEL_ID_STR = os.environ.get("DISCORD_CHANNEL_ID")

    if not TOKEN:
        raise ValueError("DISCORD_TOKEN が未設定です")
    if not CHANNEL_ID_STR:
        raise ValueError("DISCORD_CHANNEL_ID が未設定です")
    if not CHANNEL_ID_STR.isdigit():
        raise ValueError(f"DISCORD_CHANNEL_ID が数値形式ではありません: {CHANNEL_ID_STR}")

    CHANNEL_ID = int(CHANNEL_ID_STR)
    print(f"[OK] 環境変数取得成功 (CHANNEL_ID: {CHANNEL_ID})")

except Exception as e:
    print("[ERROR] 環境変数チェック中に例外発生:")
    traceback.print_exc()
    sys.exit(1)

# =========================
# Botセットアップ
# =========================
print("[STEP 3] Bot 初期化")

try:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    print("[OK] Bot オブジェクト生成成功")
except Exception as e:
    print("[ERROR] Bot初期化中に例外発生:")
    traceback.print_exc()
    sys.exit(1)

# =========================
# Nitter 設定
# =========================
NITTER_URLS = [
    "https://nitter.poast.org/CryptoJPTrans",
    "https://nitter.poast.org/angorou7"
]
last_post_urls = {}

# =========================
# 定期実行関数
# =========================
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
        print("[EXCEPTION] チャンネル取得エラー:")
        traceback.print_exc()
        return

    for url in NITTER_URLS:
        print(f"[CHECK] {url} の投稿チェック開始")
        try:
            response = requests.get(url, timeout=10)
            print(f"[DEBUG] ステータスコード: {response.status_code}")
            if response.status_code != 200:
                print(f"[WARN] {url} の取得失敗")
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
                print(f"[WARN] {url}: 必要要素が見つかりません")
                continue

            tweet_url = f"https://twitter.com{link['href']}"
            tweet_text = content.text.strip()
            user = url.split('/')[-1]

            if tweet_url != last_post_urls.get(url):
                print(f"[NEW] 新規投稿: {tweet_url}")
                last_post_urls[url] = tweet_url
                await channel.send(f"📝 [{user}] 新しい投稿がありました！\n{tweet_text}\n{tweet_url}")
            else:
                print(f"[INFO] {url}: 既に投稿済みです")

        except Exception as e:
            print(f"[EXCEPTION] 投稿チェック中エラー: {url}")
            traceback.print_exc()

# =========================
# Bot起動後のイベント処理
# =========================
@bot.event
async def on_ready():
    print("=" * 60)
    print(f"[READY] Bot logged in as {bot.user} (ID: {bot.user.id})")
    print("=" * 60)

    try:
        print("[STEP] 即時 fetch_and_post 実行")
        await fetch_and_post()
        print("[STEP] fetch_and_post 実行完了")

        print("[STEP] fetch_and_post.start() 実行")
        fetch_and_post.start()
        print("[STEP] fetch_and_post.start() 完了")
    except Exception as e:
        print("[ERROR] on_ready() 内での例外:")
        traceback.print_exc()

# =========================
# Bot 実行
# =========================
print("[STEP 4] bot.run() 実行開始")

try:
    bot.run(TOKEN)
except Exception as e:
    print("[EXCEPTION] bot.run() でのエラー:")
    traceback.print_exc()
    sys.exit(1)
