import os
import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands
import asyncio
import logging
from datetime import datetime

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 環境変数からトークンとチャンネルIDを取得
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))

# Botインスタンスの作成
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Nitterインスタンスの候補リスト（より多くの候補）
NITTER_INSTANCES = [
    "https://nitter.tiekoetter.com",
    "https://nitter.privacyredirect.com",
    "https://nitter.poast.org",
    "https://nitter.net",
    "https://nitter.it",
    "https://nitter.42l.fr",
    "https://nitter.pussthecat.org"
]

# 監視対象のアカウント
TARGET_ACCOUNTS = ["CryptoJPTrans", "angorou7"]

# 最新投稿URLの保存辞書
last_post_urls = {account: None for account in TARGET_ACCOUNTS}

def fetch_latest_post(account, max_retries=3):
    """アカウントの最新投稿を取得"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    for base_url in NITTER_INSTANCES:
        url = f"{base_url}/{account}"
        retries = 0
        
        while retries < max_retries:
            try:
                logger.info(f"Trying {url} (attempt {retries + 1})")
                res = requests.get(url, headers=headers, timeout=15)
                
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'html.parser')
                    
                    # 複数のセレクタパターンを試行
                    selectors = [
                        'div.tweet-body a[href*="/status/"]',
                        'article .tweet-link',
                        '.timeline-item .tweet-link',
                        'a[href*="/status/"]'
                    ]
                    
                    for selector in selectors:
                        link_tags = soup.select(selector)
                        if link_tags:
                            # 最初の（最新の）投稿リンクを返す
                            href = link_tags[0].get('href')
                            if href and '/status/' in href:
                                full_url = base_url + href if href.startswith('/') else href
                                logger.info(f"Found post for {account}: {full_url}")
                                return full_url
                    
                    logger.warning(f"No post links found for {account} on {base_url}")
                else:
                    logger.warning(f"{url} returned status code {res.status_code}")
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout for {url}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error for {url}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error for {url}: {e}")
            
            retries += 1
        
        # このインスタンスでは成功しなかったので次を試す
        continue
    
    logger.error(f"Failed to fetch latest post for {account} from all instances")
    return None

async def check_and_post_updates():
    """新規投稿をチェックしてDiscordに送信"""
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)
    
    if not channel:
        logger.error("Discord channel not found")
        return
    
    logger.info("Checking for new posts...")
    
    for account in TARGET_ACCOUNTS:
        try:
            logger.info(f"Checking {account}...")
            latest_post = fetch_latest_post(account)
            
            if latest_post and last_post_urls[account] != latest_post:
                logger.info(f"New post found for {account}: {latest_post}")
                last_post_urls[account] = latest_post
                
                # Discord に送信
                embed = discord.Embed(
                    title=f"🆕 新規投稿 - @{account}",
                    description=f"[投稿を見る]({latest_post})",
                    color=0x1DA1F2,  # Twitter blue
                    timestamp=datetime.utcnow()
                )
                embed.set_footer(text="X (Twitter) Monitor Bot")
                
                await channel.send(embed=embed)
                logger.info(f"Posted update for {account} to Discord")
            elif latest_post:
                logger.info(f"No new posts for {account}")
            else:
                logger.warning(f"Failed to fetch posts for {account}")
                
        except Exception as e:
            logger.error(f"Error checking {account}: {e}")

# 定期実行タスク（5分間隔）
@tasks.loop(minutes=5)
async def periodic_check():
    await check_and_post_updates()

@periodic_check.before_loop
async def before_periodic_check():
    await bot.wait_until_ready()
    logger.info("Bot is ready, starting periodic checks...")

@bot.event
async def on_ready():
    logger.info(f"Bot logged in as {bot.user} (ID: {bot.user.id})")
    
    # 初回チェック実行
    await check_and_post_updates()
    
    # 定期チェック開始
    if not periodic_check.is_running():
        periodic_check.start()

# 手動チェックコマンド（デバッグ用）
@bot.command()
async def check(ctx):
    """手動で投稿チェックを実行"""
    if ctx.author.guild_permissions.administrator:
        await ctx.send("🔍 手動チェックを開始します...")
        await check_and_post_updates()
        await ctx.send("✅ チェック完了！")
    else:
        await ctx.send("❌ このコマンドは管理者のみ使用できます。")

# ステータスコマンド
@bot.command()
async def status(ctx):
    """ボットの状態を確認"""
    embed = discord.Embed(title="📊 Bot Status", color=0x00ff00)
    embed.add_field(name="監視アカウント", value="\n".join(TARGET_ACCOUNTS), inline=False)
    embed.add_field(name="定期チェック", value="✅ 動作中" if periodic_check.is_running() else "❌ 停止中", inline=True)
    embed.add_field(name="チェック間隔", value="5分", inline=True)
    await ctx.send(embed=embed)

if __name__ == '__main__':
    logger.info("Starting Discord Bot...")
    logger.info(f"Monitoring accounts: {TARGET_ACCOUNTS}")
    logger.info(f"Target channel ID: {CHANNEL_ID}")
    
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
