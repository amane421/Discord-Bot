import os
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands
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

# Nitterインスタンスの候補リスト（2025年5月時点で動作が確認されているもの）
NITTER_INSTANCES = [
    "https://nitter.cz",
    "https://nitter.poast.org", 
    "https://nitter.privacydev.net",
    "https://nitter.riverside.rocks",
    "https://nitter.ktachibana.party",
    "https://nitter.fly.dev",
    "https://n.l5.ca",
    "https://nitter.moomoo.me",
    "https://bird.habedieeh.re",
    "https://nitter.rawbit.ninja",
    "https://nitter.hu",
    "https://tweet.lambda.dance"
]

# 監視対象のアカウント
TARGET_ACCOUNTS = ["CryptoJPTrans", "angorou7"]

# 最新投稿URLの保存辞書
last_post_urls = {account: None for account in TARGET_ACCOUNTS}

async def fetch_latest_post(account, max_retries=2, debug_mode=False):
    """アカウントの最新投稿を非同期で取得"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    timeout = aiohttp.ClientTimeout(total=8)  # 短いタイムアウト
    
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        for base_url in NITTER_INSTANCES:
            url = f"{base_url}/{account}"
            retries = 0
            
            while retries < max_retries:
                try:
                    logger.info(f"Trying {url} (attempt {retries + 1})")
                    
                    async with session.get(url) as response:
                        if response.status == 200:
                            text = await response.text()
                            
                            # Bot検証ページかどうかチェック
                            if "Making sure you're not a bot" in text or "Just a moment" in text:
                                logger.warning(f"Bot verification page detected on {base_url}")
                                break  # 次のインスタンスへ
                            
                            # 空白またはエラーページかどうかチェック
                            if len(text.strip()) < 500 or "<!-- Blank -->" in text:
                                logger.warning(f"Empty or blank page on {base_url}")
                                break  # 次のインスタンスへ
                            
                            soup = BeautifulSoup(text, 'html.parser')
                            
                            # デバッグモード: HTMLの構造を確認
                            if debug_mode:
                                logger.info(f"=== DEBUG: HTML structure for {account} on {base_url} ===")
                                title = soup.find('title')
                                logger.info(f"Page title: {title.text if title else 'No title'}")
                                
                                all_links = soup.find_all('a', href=True)
                                status_links = [link for link in all_links if '/status/' in link.get('href', '')]
                                logger.info(f"Found {len(status_links)} status links")
                                
                                for i, link in enumerate(status_links[:3]):
                                    logger.info(f"Status link {i+1}: {link.get('href')} - Text: {link.get_text()[:50]}")
                            
                            # より包括的なセレクタパターンを試行
                            selectors = [
                                '.tweet-link[href*="/status/"]',
                                'a.tweet-link[href*="/status/"]',
                                '.timeline-item .tweet-link',
                                'div.tweet-body a[href*="/status/"]',
                                '.tweet-header a[href*="/status/"]',
                                'a[href*="/status/"]',
                                '[href*="/status/"]',
                                '.main-tweet a[href*="/status/"]',
                                '.tweet a[href*="/status/"]',
                                'article a[href*="/status/"]',
                                '.timeline-tweet a[href*="/status/"]',
                                '.tweet-content a[href*="/status/"]',
                                '.timeline .tweet a[href*="/status/"]',
                                '.post a[href*="/status/"]',
                                '.status a[href*="/status/"]'
                            ]
                            
                            for selector in selectors:
                                link_tags = soup.select(selector)
                                if link_tags:
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
                            
                            logger.warning(f"No post links found for {account} on {base_url}")
                            break  # 次のインスタンスへ
                            
                        elif response.status == 429:
                            logger.warning(f"Rate limited on {base_url}")
                            await asyncio.sleep(5)  # 短い待機
                            retries += 1
                            continue
                        else:
                            logger.warning(f"{url} returned status code {response.status}")
                            break  # 次のインスタンスへ
                            
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout for {url}")
                except aiohttp.ClientError as e:
                    logger.error(f"Request error for {url}: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error for {url}: {e}")
                
                retries += 1
            
            # 短い遅延後、次のインスタンスを試す
            await asyncio.sleep(0.1)
    
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
            latest_post = await fetch_latest_post(account, debug_mode=debug_mode)
            
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

# インスタンス状態の定期チェック（1日1回）
@tasks.loop(hours=24)
async def daily_instance_check():
    """毎日Nitterインスタンスの状態をチェック"""
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)
    
    if not channel:
        return
    
    logger.info("Running daily instance health check...")
    
    working_count = 0
    timeout = aiohttp.ClientTimeout(total=5)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        for instance in NITTER_INSTANCES[:5]:  # 最初の5つだけチェック
            try:
                test_url = f"{instance}/elonmusk"
                async with session.get(test_url) as response:
                    if response.status == 200:
                        text = await response.text()
                        if ("Making sure you're not a bot" not in text and 
                            len(text.strip()) > 500):
                            working_count += 1
            except:
                continue
    
    # 動作中のインスタンスが少ない場合に警告
    if working_count < 2:
        embed = discord.Embed(
            title="⚠️ Nitterインスタンス状態警告",
            description=f"現在動作中のインスタンス: {working_count}/5\n\n代替手段の検討をお勧めします。\n`!alternatives` コマンドで詳細を確認してください。",
            color=0xFF6B6B
        )
        await channel.send(embed=embed)

@periodic_check.before_loop
async def before_periodic_check():
    await bot.wait_until_ready()
    logger.info("Bot is ready, starting periodic checks...")

@daily_instance_check.before_loop
async def before_daily_check():
    await bot.wait_until_ready()
    logger.info("Starting daily instance health checks...")

@bot.event
async def on_ready():
    logger.info(f"Bot logged in as {bot.user} (ID: {bot.user.id})")
    
    # 初回チェック実行（デバッグモード有効）
    logger.info("Running initial check with debug mode enabled...")
    await check_and_post_updates(debug_mode=True)
    
    # 定期チェック開始
    if not periodic_check.is_running():
        periodic_check.start()
        
    # 日次インスタンスチェック開始
    if not daily_instance_check.is_running():
        daily_instance_check.start()

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
        result = await fetch_latest_post(account, debug_mode=True)
        if result:
            await ctx.send(f"✅ 投稿が見つかりました: {result}")
        else:
            await ctx.send("❌ 投稿が見つかりませんでした。ログを確認してください。")
    except Exception as e:
        await ctx.send(f"❌ エラーが発生しました: {str(e)}")
        logger.error(f"Debug command error: {e}")

# インスタンス状態確認コマンド
@bot.command()
async def test_instances(ctx):
    """全てのNitterインスタンスの状態をテスト"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ このコマンドは管理者のみ使用できます。")
        return
    
    await ctx.send("🔍 Nitterインスタンスの状態をテストしています...")
    
    working_instances = []
    bot_protected = []
    failed_instances = []
    
    timeout = aiohttp.ClientTimeout(total=5)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        for instance in NITTER_INSTANCES:
            try:
                test_url = f"{instance}/elonmusk"  # テスト用の有名アカウント
                async with session.get(test_url) as response:
                    if response.status == 200:
                        text = await response.text()
                        if "Making sure you're not a bot" in text:
                            bot_protected.append(instance)
                        elif len(text.strip()) < 500:
                            failed_instances.append(f"{instance} (empty page)")
                        else:
                            # 実際に投稿リンクがあるかチェック
                            soup = BeautifulSoup(text, 'html.parser')
                            status_links = soup.find_all('a', href=True)
                            has_status = any('/status/' in link.get('href', '') for link in status_links)
                            
                            if has_status:
                                working_instances.append(instance)
                            else:
                                failed_instances.append(f"{instance} (no posts found)")
                    else:
                        failed_instances.append(f"{instance} (HTTP {response.status})")
                        
            except Exception as e:
                failed_instances.append(f"{instance} (Error: {str(e)[:50]})")
    
    # 結果を報告
    embed = discord.Embed(title="📊 Nitterインスタンス状態レポート", color=0x1DA1F2)
    
    if working_instances:
        embed.add_field(
            name="✅ 動作中",
            value="\n".join(working_instances[:5]),  # 最大5つまで表示
            inline=False
        )
    
    if bot_protected:
        embed.add_field(
            name="🛡️ Bot検証あり",
            value="\n".join(bot_protected[:5]),
            inline=False
        )
    
    if failed_instances:
        embed.add_field(
            name="❌ 利用不可",
            value="\n".join(failed_instances[:10]),
            inline=False
        )
    
    embed.add_field(
        name="📝 推奨事項",
        value="動作中のインスタンスが少ない場合は、Twitter API の利用を検討してください。",
        inline=False
    )
    
    await ctx.send(embed=embed)

# 代替手段の提案コマンド
@bot.command()
async def alternatives(ctx):
    """Nitter以外の代替手段を表示"""
    embed = discord.Embed(
        title="🔄 代替手段の提案",
        description="Nitterが不安定な場合の他のオプション",
        color=0xFFA500
    )
    
    embed.add_field(
        name="1. Twitter API v2 (推奨)",
        value="• 最も安定した方法\n• 月間投稿数制限あり（無料枠）\n• 開発者アカウント必要",
        inline=False
    )
    
    embed.add_field(
        name="2. RSS/Atom フィード",
        value="• RSSBridge等のサービス利用\n• `https://rss-bridge.org/bridge01/#bridge-TwitterBridge`",
        inline=False
    )
    
    embed.add_field(
        name="3. 他のプロキシサービス",
        value="• TweetDeck等の代替サービス\n• 定期的に利用可能性をチェック必要",
        inline=False
    )
    
    embed.add_field(
        name="📚 参考リンク",
        value="[Twitter API Documentation](https://developer.twitter.com/en/docs/twitter-api)\n[RSSBridge](https://rss-bridge.org/)",
        inline=False
    )
    
    await ctx.send(embed=embed)

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
