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
    "https://nitter.it",
    "https://nitter.unixfox.eu",
    "https://nitter.namazso.eu",
    "https://nitter.fdn.fr",
    "https://nitter.1d4.us",
    "https://nitter.kavin.rocks",
    "https://nitter.domain.glass"
]

# 監視対象のアカウント
TARGET_ACCOUNTS = ["CryptoJPTrans", "angorou7"]

# 最新投稿URLの保存辞書
last_post_urls = {account: None for account in TARGET_ACCOUNTS}

def fetch_latest_post(account, max_retries=3, debug_mode=False):
    """アカウントの最新投稿を取得"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
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
                    
                    # デバッグモード: HTMLの構造を確認
                    if debug_mode:
                        logger.info(f"=== DEBUG: HTML structure for {account} on {base_url} ===")
                        # タイトルを確認
                        title = soup.find('title')
                        logger.info(f"Page title: {title.text if title else 'No title'}")
                        
                        # 全てのリンクを確認
                        all_links = soup.find_all('a', href=True)
                        status_links = [link for link in all_links if '/status/' in link.get('href', '')]
                        logger.info(f"Found {len(status_links)} status links")
                        
                        for i, link in enumerate(status_links[:3]):  # 最初の3つだけ表示
                            logger.info(f"Status link {i+1}: {link.get('href')} - Text: {link.get_text()[:50]}")
                        
                        # よく使われるクラス名を確認
                        tweet_containers = soup.find_all(['div', 'article'], class_=True)
                        unique_classes = set()
                        for container in tweet_containers:
                            if container.get('class'):
                                unique_classes.update(container.get('class'))
                        logger.info(f"Found classes: {sorted(list(unique_classes))[:10]}")  # 最初の10個
                    
                    # より包括的なセレクタパターンを試行
                    selectors = [
                        # 一般的なNitterセレクタ
                        '.tweet-link[href*="/status/"]',
                        'a.tweet-link[href*="/status/"]',
                        '.timeline-item .tweet-link',
                        'div.tweet-body a[href*="/status/"]',
                        '.tweet-header a[href*="/status/"]',
                        
                        # より広範なセレクタ
                        'a[href*="/status/"]',
                        '[href*="/status/"]',
                        
                        # 特定のNitterバージョン対応
                        '.main-tweet a[href*="/status/"]',
                        '.tweet a[href*="/status/"]',
                        'article a[href*="/status/"]'
                    ]
                    
                    for selector in selectors:
                        link_tags = soup.select(selector)
                        if link_tags:
                            # 最初の（最新の）投稿リンクを返す
                            href = link_tags[0].get('href')
                            if href and '/status/' in href:
                                # 相対URLを絶対URLに変換
                                if href.startswith('/'):
                                    full_url = base_url + href
                                elif href.startswith('http'):
                                    full_url = href
                                else:
                                    full_url = base_url + '/' + href
                                
                                logger.info(f"Found post for {account} using selector '{selector}': {full_url}")
                                return full_url
                    
                    # デバッグ情報: HTMLの一部を出力
                    if debug_mode:
                        logger.info(f"HTML snippet (first 1000 chars): {res.text[:1000]}")
                    
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

async def check_and_post_updates(debug_mode=False):
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
            latest_post = fetch_latest_post(account, debug_mode=debug_mode)
            
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
    
    # 初回チェック実行（デバッグモード有効）
    logger.info("Running initial check with debug mode enabled...")
    await check_and_post_updates(debug_mode=True)
    
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

# デバッグモードでのチェックコマンド
@bot.command()
async def debug_check(ctx):
    """デバッグモードで投稿チェックを実行"""
    if ctx.author.guild_permissions.administrator:
        await ctx.send("🔍 デバッグモードでチェックを開始します...")
        await check_and_post_updates(debug_mode=True)
        await ctx.send("✅ デバッグチェック完了！ログを確認してください。")
    else:
        await ctx.send("❌ このコマンドは管理者のみ使用できます。")

# 特定アカウントのデバッグ
@bot.command()
async def debug_account(ctx, account=None):
    """特定アカウントのHTMLを詳細デバッグ"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ このコマンドは管理者のみ使用できます。")
        return
    
    if not account:
        await ctx.send("使用方法: `!debug_account [アカウント名]`")
        return
    
    if account not in TARGET_ACCOUNTS:
        await ctx.send(f"❌ `{account}` は監視対象ではありません。対象: {', '.join(TARGET_ACCOUNTS)}")
        return
    
    await ctx.send(f"🔍 {account} のデバッグを開始します...")
    
    try:
        result = fetch_latest_post(account, debug_mode=True)
        if result:
            await ctx.send(f"✅ 投稿が見つかりました: {result}")
        else:
            await ctx.send("❌ 投稿が見つかりませんでした。ログを確認してください。")
    except Exception as e:
        await ctx.send(f"❌ エラーが発生しました: {str(e)}")
        logger.error(f"Debug command error: {e}")

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
