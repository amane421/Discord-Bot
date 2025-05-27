import os
import discord
from discord.ext import tasks, commands
import aiohttp
import asyncio
import logging
from datetime import datetime, timedelta
import json

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 環境変数
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID")) if os.environ.get("CHANNEL_ID") else None
TWITTER_BEARER_TOKEN = os.environ.get("TWITTER_BEARER_TOKEN")

# 🎯 監視対象のアカウント（ここを変更してください）
TARGET_ACCOUNTS = {
    "CryptoJPTrans": None,  # ← 必要に応じて変更
    "angorou7": None        # ← 必要に応じて変更
    # "他のアカウント名": None,  # ← 追加したい場合
}

# Botインスタンス
intents = discord.Intents.default()
intents.message_content = True  # メッセージ内容を読み取るため
bot = commands.Bot(command_prefix="!", intents=intents)

# 最新ツイートIDの保存
last_tweet_ids = {account: None for account in TARGET_ACCOUNTS}

# レート制限管理
class RateLimiter:
    def __init__(self):
        self.requests_per_window = 75  # 15分間に75回
        self.window_duration = 900    # 15分 = 900秒
        self.requests = []
        self.monthly_count = 0
        self.monthly_limit = 10000
        self.month_start = datetime.now()
    
    async def wait_if_needed(self):
        """必要に応じて待機"""
        now = datetime.now()
        
        # 月間制限チェック
        if (now - self.month_start).days >= 30:
            self.monthly_count = 0
            self.month_start = now
        
        if self.monthly_count >= self.monthly_limit:
            logger.error("Monthly limit exceeded! Waiting until next month...")
            return False
        
        # 15分間のウィンドウをクリア
        cutoff = now - timedelta(seconds=self.window_duration)
        self.requests = [req_time for req_time in self.requests if req_time > cutoff]
        
        # レート制限チェック
        if len(self.requests) >= self.requests_per_window:
            sleep_time = self.window_duration - (now - self.requests[0]).total_seconds()
            if sleep_time > 0:
                logger.warning(f"Rate limit reached. Waiting {sleep_time:.1f} seconds...")
                await asyncio.sleep(sleep_time)
                return await self.wait_if_needed()
        
        # リクエストを記録
        self.requests.append(now)
        self.monthly_count += 1
        logger.info(f"API Request #{self.monthly_count}/10000 this month")
        return True

class TwitterAPI:
    def __init__(self, bearer_token):
        if not bearer_token:
            raise ValueError("Bearer token is required")
        self.bearer_token = bearer_token
        self.base_url = "https://api.twitter.com/2"
        
    async def get_user_id(self, username):
        """ユーザー名からユーザーIDを取得"""
        if not await rate_limiter.wait_if_needed():
            return None
            
        url = f"{self.base_url}/users/by/username/{username}"
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Got user ID for {username}: {data['data']['id']}")
                        return data["data"]["id"]
                    elif response.status == 429:
                        logger.error("Rate limit exceeded from Twitter API")
                        return None
                    elif response.status == 401:
                        logger.error("Invalid Twitter Bearer Token")
                        return None
                    elif response.status == 404:
                        logger.error(f"User {username} not found")
                        return None
                    else:
                        logger.error(f"Failed to get user ID for {username}: HTTP {response.status}")
                        response_text = await response.text()
                        logger.error(f"Response: {response_text}")
                        return None
        except Exception as e:
            logger.error(f"Error getting user ID for {username}: {e}")
            return None
    
    async def get_user_tweets(self, user_id, max_results=5):
        """ユーザーの最新ツイートを取得（画像・メディア対応）"""
        if not await rate_limiter.wait_if_needed():
            return []
            
        url = f"{self.base_url}/users/{user_id}/tweets"
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        params = {
            "max_results": min(max_results, 5),  # 最大5件に制限
            "tweet.fields": "created_at,attachments",
            "media.fields": "url,preview_image_url,type",
            "expansions": "attachments.media_keys",
            "exclude": "retweets,replies"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        tweets = data.get("data", [])
                        media_info = data.get("includes", {}).get("media", [])
                        
                        # ツイートにメディア情報を付与
                        for tweet in tweets:
                            tweet['media_info'] = []
                            if 'attachments' in tweet and 'media_keys' in tweet['attachments']:
                                for media_key in tweet['attachments']['media_keys']:
                                    for media in media_info:
                                        if media['media_key'] == media_key:
                                            tweet['media_info'].append(media)
                        
                        logger.info(f"Retrieved {len(tweets)} tweets for user {user_id}")
                        return tweets
                    elif response.status == 429:
                        logger.error("Rate limit exceeded from Twitter API")
                        return []
                    elif response.status == 401:
                        logger.error("Invalid Twitter Bearer Token")
                        return []
                    else:
                        logger.error(f"Failed to get tweets for user {user_id}: HTTP {response.status}")
                        response_text = await response.text()
                        logger.error(f"Response: {response_text}")
                        return []
        except Exception as e:
            logger.error(f"Error getting tweets for user {user_id}: {e}")
            return []

# 初期化時のエラーハンドリング強化
def validate_environment():
    """環境変数の検証"""
    errors = []
    
    if not DISCORD_TOKEN:
        errors.append("DISCORD_TOKEN is not set")
    
    if not CHANNEL_ID:
        errors.append("CHANNEL_ID is not set or invalid")
    
    if not TWITTER_BEARER_TOKEN:
        errors.append("TWITTER_BEARER_TOKEN is not set")
    
    if errors:
        for error in errors:
            logger.error(error)
        return False
    
    return True

# 環境変数検証後にTwitterAPI初期化
if validate_environment():
    rate_limiter = RateLimiter()
    twitter_api = TwitterAPI(TWITTER_BEARER_TOKEN)
else:
    logger.error("Environment validation failed. Exiting...")
    exit(1)

async def initialize_user_ids():
    """起動時にユーザーIDを取得"""
    logger.info(f"Initializing user IDs for accounts: {list(TARGET_ACCOUNTS.keys())}")
    
    for username in TARGET_ACCOUNTS:
        try:
            user_id = await twitter_api.get_user_id(username)
            if user_id:
                TARGET_ACCOUNTS[username] = user_id
                logger.info(f"✅ Initialized user ID for {username}: {user_id}")
            else:
                logger.error(f"❌ Failed to get user ID for {username}")
            
            # ユーザーID取得間でも少し待機
            await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"Error initializing {username}: {e}")

async def check_and_post_updates():
    """新規ツイートをチェックしてDiscordに送信"""
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)
    
    if not channel:
        logger.error(f"Discord channel not found (ID: {CHANNEL_ID})")
        return
    
    logger.info("Checking for new tweets (rate-limited)...")
    
    active_accounts = {k: v for k, v in TARGET_ACCOUNTS.items() if v is not None}
    logger.info(f"Active accounts: {len(active_accounts)}/{len(TARGET_ACCOUNTS)}")
    
    for username, user_id in active_accounts.items():
        try:
            logger.info(f"Checking {username} (ID: {user_id})...")
            tweets = await twitter_api.get_user_tweets(user_id, max_results=1)
            
            if tweets:
                latest_tweet = tweets[0]
                tweet_id = latest_tweet["id"]
                
                if last_tweet_ids[username] != tweet_id:
                    logger.info(f"🆕 New tweet found for {username}: {tweet_id}")
                    last_tweet_ids[username] = tweet_id
                    
                    # Discord埋め込み（完全クリーン版）
                    embed = discord.Embed(
                        description=latest_tweet["text"],
                        color=0x1DA1F2
                    )
                    
                    # 画像がある場合は最初の画像を表示
                    if latest_tweet.get('media_info'):
                        for media in latest_tweet['media_info']:
                            if media['type'] == 'photo' and 'url' in media:
                                embed.set_image(url=media['url'])
                                break  # 最初の画像のみ表示
                            elif media['type'] == 'video' and 'preview_image_url' in media:
                                embed.set_image(url=media['preview_image_url'])
                                break
                    
                    await channel.send(embed=embed)
                    logger.info(f"✅ Posted update for {username} to Discord")
                else:
                    logger.info(f"No new tweets for {username}")
            else:
                logger.warning(f"No tweets found for {username}")
            
            # アカウント間で待機（レート制限考慮）
            await asyncio.sleep(5)
                
        except Exception as e:
            logger.error(f"Error checking {username}: {e}")

# 定期実行タスク（30分間隔 - レート制限を考慮）
@tasks.loop(minutes=30)
async def periodic_check():
    await check_and_post_updates()

@periodic_check.before_loop
async def before_periodic_check():
    await bot.wait_until_ready()
    await initialize_user_ids()
    logger.info("Twitter API bot is ready, starting periodic checks...")

@bot.event
async def on_ready():
    logger.info(f"Bot logged in as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Target channel: {CHANNEL_ID}")
    logger.info(f"Monitoring accounts: {list(TARGET_ACCOUNTS.keys())}")
    
    # 初回チェック実行
    logger.info("Running initial check...")
    await check_and_post_updates()
    
    # 定期チェック開始
    if not periodic_check.is_running():
        periodic_check.start()

# 手動チェックコマンド
@bot.command()
async def check(ctx):
    """手動でツイートチェックを実行"""
    if ctx.author.guild_permissions.administrator:
        await ctx.send("🔍 手動チェックを開始します...")
        await check_and_post_updates()
        await ctx.send("✅ チェック完了！")
    else:
        await ctx.send("❌ このコマンドは管理者のみ使用できます。")

# レート制限状況確認コマンド
@bot.command()
async def rate_status(ctx):
    """レート制限状況を確認"""
    embed = discord.Embed(title="📊 Twitter API レート制限状況", color=0x1DA1F2)
    
    # 月間使用量
    remaining_monthly = rate_limiter.monthly_limit - rate_limiter.monthly_count
    embed.add_field(
        name="月間使用量",
        value=f"{rate_limiter.monthly_count:,}/{rate_limiter.monthly_limit:,}\n残り: {remaining_monthly:,}",
        inline=False
    )
    
    # 15分間のウィンドウ
    now = datetime.now()
    cutoff = now - timedelta(seconds=900)
    recent_requests = [req for req in rate_limiter.requests if req > cutoff]
    
    embed.add_field(
        name="15分間の使用量",
        value=f"{len(recent_requests)}/75",
        inline=True
    )
    
    # 次回リセット時刻
    if rate_limiter.requests:
        next_reset = rate_limiter.requests[0] + timedelta(seconds=900)
        embed.add_field(
            name="次回リセット",
            value=f"<t:{int(next_reset.timestamp())}:R>",
            inline=True
        )
    
    # 月間リセット
    month_reset = rate_limiter.month_start + timedelta(days=30)
    embed.add_field(
        name="月間リセット",
        value=f"<t:{int(month_reset.timestamp())}:D>",
        inline=True
    )
    
    await ctx.send(embed=embed)

# ユーザーID確認コマンド
@bot.command()
async def user_ids(ctx):
    """監視対象アカウントのユーザーIDを確認"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ このコマンドは管理者のみ使用できます。")
        return
    
    embed = discord.Embed(title="👤 監視対象アカウント", color=0x1DA1F2)
    
    for username, user_id in TARGET_ACCOUNTS.items():
        status = "✅" if user_id else "❌"
        embed.add_field(
            name=f"{status} @{username}",
            value=f"ID: {user_id or 'Not found'}",
            inline=False
        )
    
    await ctx.send(embed=embed)

# 設定情報表示コマンド
@bot.command()
async def config(ctx):
    """Bot設定情報を表示"""
    embed = discord.Embed(title="⚙️ Bot設定情報", color=0x00ff00)
    embed.add_field(name="チェック間隔", value="30分", inline=True)
    embed.add_field(name="レート制限", value="75回/15分", inline=True)
    embed.add_field(name="月間制限", value="10,000ツイート", inline=True)
    embed.add_field(name="監視アカウント数", value=f"{len(TARGET_ACCOUNTS)}個", inline=True)
    embed.add_field(name="API バージョン", value="Twitter API v2", inline=True)
    embed.add_field(name="プラン", value="Basic (無料)", inline=True)
    embed.add_field(name="サービス", value="Background Worker", inline=True)
    embed.add_field(name="機能", value="ツイート本文 + 画像対応", inline=True)
    
    await ctx.send(embed=embed)

if __name__ == '__main__':
    logger.info("=== Starting Twitter API Discord Bot ===")
    logger.info(f"Monitoring accounts: {list(TARGET_ACCOUNTS.keys())}")
    logger.info(f"Target channel ID: {CHANNEL_ID}")
    
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        exit(1)
