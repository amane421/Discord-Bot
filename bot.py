import os
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands

# 環境変数からトークンとチャンネルIDを取得
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID"))  # 環境変数名の確認

# 対象NitterアカウントのURLリスト
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

    # チャンネル取得
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("[ERROR] Discordチャンネルが見つかりませんでした")
        return
    print(f"[INFO] チャンネル取得成功: {channel.name}")

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
                print(f"[WARN] {url}: 必要な要素が見つかりません")
                continue

            tweet_url = f"https://twitter.com{link['href']}"
            tweet_text = content.text.strip()

            if url not in last_post_urls:
                print(f"[INIT] {url}: 初回読み込みとしてURLを記録")
                last_post_urls[url] = tweet_url
                continue

            if tweet_url != last_post_urls[url]:
                print(f"[NEW] 新規投稿検出: {tweet_url}")
                last_post_urls[url] = tweet_url
                user = url.split('/')[-1]
                await channel.send(f"📝 [{user}] 新しい投稿がありました！\n{tweet_text}\n{tweet_url}")
            else:
                print(f"[INFO] {url}: 新しい投稿はありません")

        except Exception as e:
            print(f"[EXCEPTION] {url}: {e}")

@bot.event
async def on_ready():
    print(f"[READY] Bot logged in as {bot.user}")
    fetch_and_post.start()

# Bot起動
bot.run(TOKEN)
