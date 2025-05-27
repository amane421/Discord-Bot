import os
import aiohttp
import asyncio
import random
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands
import logging
from datetime import datetime
import json
import brotli  # Brotli圧縮サポート

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 環境変数
TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))

# Botインスタンス
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# 更新されたNitterインスタンス（動作確認済み）
NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.tiekoetter.com", 
    "https://nitter.privacyredirect.com",
    "https://lightbrd.com",  # 新発見
    "https://nitter.cz",
    "https://nitter.privacydev.net"
]

# 監視対象アカウント
TARGET_ACCOUNTS = ["CryptoJPTrans", "angorou7"]
last_post_urls = {account: None for account in TARGET_ACCOUNTS}

def get_realistic_headers():
    """リアルなブラウザヘッダーをランダムに生成"""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
    ]
    
    accept_languages = [
        "en-US,en;q=0.9",
        "en-US,en;q=0.9,ja;q=0.8",
        "en-GB,en;q=0.9",
        "ja,en-US;q=0.9,en;q=0.8"
    ]
    
    return {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": random.choice(accept_languages),
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }

async def fetch_with_stealth(session, url, max_retries=2):
    """ステルス機能付きでページを取得"""
    for attempt in range(max_retries):
        try:
            # ランダムな遅延（人間らしい行動をシミュレート）
            await asyncio.sleep(random.uniform(1.0, 3.0))
            
            headers = get_realistic_headers()
            
            async with session.get(url, headers=headers) as response:
                logger.info(f"Attempt {attempt + 1} - {url} - Status: {response.status}")
                
                if response.status == 200:
                    text = await response.text()
                    
                    # Bot検証ページの検出
                    bot_indicators = [
                        "Making sure you're not a bot",
                        "Just a moment",
                        "Checking your browser",
                        "Please wait",
                        "Ray ID:",
                        "cloudflare"
                    ]
                    
                    text_lower = text.lower()
                    if any(indicator.lower() in text_lower for indicator in bot_indicators):
                        logger.warning(f"Bot verification page detected on {url}")
                        if attempt < max_retries - 1:
                            # より長い遅延後にリトライ
                            await asyncio.sleep(random.uniform(5.0, 10.0))
                            continue
                        return None, "bot_verification"
                    
                    # 空白ページの検出
                    if len(text.strip()) < 500:
                        logger.warning(f"Empty page detected on {url}")
                        return None, "empty_page"
                    
                    # 成功
                    logger.info(f"Successfully fetched {url} ({len(text)} chars)")
                    return text, "success"
                    
                elif response.status == 403:
                    logger.warning(f"403 Forbidden for {url}")
                    return None, "forbidden"
                elif response.status == 429:
                    logger.warning(f"Rate limited for {url}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(random.uniform(10.0, 20.0))
                        continue
                    return None, "rate_limited"
                else:
                    logger.warning(f"HTTP {response.status} for {url}")
                    return None, f"http_{response.status}"
                    
        except asyncio.TimeoutError:
            logger.warning(f"Timeout for {url}")
            if attempt < max_retries - 1:
                await asyncio.sleep(random.uniform(2.0, 5.0))
                continue
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(random.uniform(2.0, 5.0))
                continue
    
    return None, "failed"

async def fetch_latest_post(account, debug_mode=False):
    """アカウントの最新投稿を取得（ステルス機能付き）"""
    # より長いタイムアウトとConnection pool設定
    timeout = aiohttp.ClientTimeout(total=15, connect=10)
    
    # TCPコネクタの設定（より現実的な接続）
    connector = aiohttp.TCPConnector(
        limit=10,
        limit_per_host=2,
        keepalive_timeout=30,
        enable_cleanup_closed=True
    )
    
    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
        cookie_jar=aiohttp.CookieJar()  # Cookieを保持
    ) as session:
        
        for base_url in NITTER_INSTANCES:
            url = f"{base_url}/{account}"
            logger.info(f"Trying {url}")
            
            # インスタンス間でランダムな遅延
            await asyncio.sleep(random.uniform(2.0, 5.0))
            
            text, status = await fetch_with_stealth(session, url)
            
            if text:
                soup = BeautifulSoup(text, 'html.parser')
                
                if debug_mode:
                    logger.info(f"=== DEBUG: {account} on {base_url} ===")
                    title = soup.find('title')
                    logger.info(f"Page title: {title.text if title else 'No title'}")
                
                # 包括的なセレクタパターン
                selectors = [
                    '.tweet-link[href*="/status/"]',
                    'a.tweet-link',
                    '.timeline-item .tweet-link',
                    'div.tweet-body a[href*="/status/"]',
                    'a[href*="/status/"]',
                    '.main-tweet a[href*="/status/"]',
                    '.tweet a[href*="/status/"]',
                    'article a[href*="/status/"]',
                    '.timeline-tweet a[href*="/status/"]'
                ]
                
                for selector in selectors:
                    links = soup.select(selector)
                    for link in links:
                        href = link.get('href')
                        if href and '/status/' in href:
                            # 絶対URLに変換
                            if href.startswith('/'):
                                full_url = base_url + href
                            elif href.startswith('http'):
                                full_url = href
                            else:
                                full_url = f"{base_url}/{href}"
                            
                            logger.info(f"Found post for {account}: {full_url}")
                            return full_url
                
                logger.warning(f"No status links found for {account} on {base_url}")
            else:
                logger.warning(f"Failed to fetch {account} from {base_url}: {status}")
    
    logger.error(f"Failed to fetch latest post for {account} from all instances")
    return None

async def check_and_post_updates(debug_mode=False):
    """新規投稿をチェックしてDiscordに送信"""
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)
    
    if not channel:
        logger.error("Discord channel not found")
        return
    
    logger.info("Checking for new posts (stealth mode)...")
    
    for account in TARGET_ACCOUNTS:
        try:
            logger.info(f"Checking {account}...")
            latest_post = await fetch_latest_post(account, debug_mode=debug_mode)
            
            if latest_post and last_post_urls[account] != latest_post:
                logger.info(f"New post found for {account}: {latest_post}")
                last_post_urls[account] = latest_post
                
                embed = discord.Embed(
                    title=f"🆕 新規投稿 - @{account}",
                    description=f"[投稿を見る]({latest_post})",
                    color=0x1DA1F2,
                    timestamp=datetime.utcnow()
                )
                embed.set_footer(text="Stealth Nitter Bot")
                
                await channel.send(embed=embed)
                logger.info(f"Posted update for {account} to Discord")
            elif latest_post:
                logger.info(f"No new posts for {account}")
            else:
                logger.warning(f"Failed to fetch posts for {account}")
                
        except Exception as e:
            logger.error(f"Error checking {account}: {e}")
        
        # アカウント間でランダムな遅延
        await asyncio.sleep(random.uniform(3.0, 8.0))

# 定期実行タスク（長めの間隔）
@tasks.loop(minutes=15)  # Bot検知を避けるため長めの間隔
async def periodic_check():
    await check_and_post_updates()

@periodic_check.before_loop
async def before_periodic_check():
    await bot.wait_until_ready()
    logger.info("Stealth bot is ready, starting periodic checks...")

@bot.event
async def on_ready():
    logger.info(f"Bot logged in as {bot.user} (ID: {bot.user.id})")
    
    # 初回チェック（デバッグモード）
    logger.info("Running initial stealth check...")
    await check_and_post_updates(debug_mode=True)
    
    if not periodic_check.is_running():
        periodic_check.start()

# コマンド類
@bot.command()
async def stealth_check(ctx):
    """ステルスモードで手動チェック"""
    if ctx.author.guild_permissions.administrator:
        await ctx.send("🥷 ステルスモードでチェックを開始します...")
        await check_and_post_updates(debug_mode=True)
        await ctx.send("✅ ステルスチェック完了！")
    else:
        await ctx.send("❌ このコマンドは管理者のみ使用できます。")

@bot.command()
async def test_stealth(ctx, account=None):
    """特定アカウントのステルステスト"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ このコマンドは管理者のみ使用できます。")
        return
    
    if not account:
        account = random.choice(TARGET_ACCOUNTS)
    
    await ctx.send(f"🔍 {account} のステルステストを開始...")
    
    try:
        result = await fetch_latest_post(account, debug_mode=True)
        if result:
            await ctx.send(f"✅ 成功！投稿URL: {result}")
        else:
            await ctx.send("❌ 投稿を取得できませんでした。ログを確認してください。")
    except Exception as e:
        await ctx.send(f"❌ エラー: {str(e)}")

@bot.command()
async def status(ctx):
    """ボット状態確認"""
    embed = discord.Embed(title="🥷 Stealth Nitter Bot Status", color=0x00ff00)
    embed.add_field(name="監視アカウント", value="\n".join(TARGET_ACCOUNTS), inline=False)
    embed.add_field(name="定期チェック", value="✅ 動作中" if periodic_check.is_running() else "❌ 停止中", inline=True)
    embed.add_field(name="チェック間隔", value="15分", inline=True)
    embed.add_field(name="インスタンス数", value=f"{len(NITTER_INSTANCES)}個", inline=True)
    embed.add_field(name="特徴", value="• ランダム遅延\n• リアルなUA\n• Cookie保持", inline=False)
    await ctx.send(embed=embed)

if __name__ == '__main__':
    logger.info("Starting Stealth Nitter Bot...")
    logger.info(f"Monitoring accounts: {TARGET_ACCOUNTS}")
    logger.info(f"Target channel ID: {CHANNEL_ID}")
    
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
