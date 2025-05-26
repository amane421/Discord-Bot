import os
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands

# 環境変数からトークンとチャンネルIDを取得
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID"))

# Nitter アカウントのURLリスト
NITTER_URLS = [
    "https://nitter.poast.org/CryptoJPTrans",
    "https://nitter.poast.org/angorou7"
]

# 各アカウントの最新投稿URLを記録
last_post_urls = {}

# Bot初期化
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@tasks.loop(minutes=60)
async def fetch_and_post():
    print("[TASK] fetch_and_post 実行開始")

    try:
        channel = bot.get_channel(CHANNEL_ID)
        if not channel:
            print(f"[ERROR] チャンネルID {CHANNEL_ID} が見つかりません。")
            return
        print(f"[INFO] チャンネル取得成功: {channel.name}")
    except Exception as e:
        print(f"[EXCEPTION] チャンネル取得エラー: {e}")
        return

    for url in NITTER_URLS:
        print(f"[CHECK] {url} の投稿チェック開始")
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                print(f"[ERROR] {url} の取得に失敗: {response.status_code}")
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
                print(f"[WARN] {url}: 必要な要素が見つかりません（link: {link}, content: {content}）")
                continue

            tweet_url = f"https://twitter.com{link['href']}"
            tweet_text = content.text.strip()

            user = url.split('/')[-1]
            is_new_post = tweet_url != last_post_urls.get(url)

            if is_new_post:
                print(f"[NEW] 新規投稿検出 or 初回通知: {tweet_url}")
                last_post_urls[url] = tweet_url
                await channel.send(f"📝 [{user}] 新しい投稿がありました！\n{tweet_text}\n{tweet_url}")
            else:
                print(f"[INFO] {url}: 新しい投稿はありません")

        except Exception as e:
            print(f"[EXCEPTION] {url}: {e}")

@bot.event
async def on_ready():
    print("=" * 40)
    print(f"[READY] Bot logged in as {bot.user}")
    print("=" * 40)

    try:
        print("[INFO] fetch_and_post を即時実行します")
        await fetch_and_post()
        print("[INFO] fetch_and_post 即時実行完了")
        
        fetch_and_post.start()
        print("[INFO] fetch_and_post のループを開始しました")
    except Exception as e:
        print(f"[EXCEPTION] on_ready でのエラー: {e}")

# Bot起動
try:
    bot.run(TOKEN)
except Exception as e:
    print(f"[EXCEPTION] Bot起動失敗: {e}")
