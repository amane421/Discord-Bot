skip_until = {}

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

# レート制限管理（無料プラン対応版）
class RateLimiter:
    def __init__(self):
        # Twitter API v2 無料プランの制限に合わせる
        self.requests_per_window = 10  # 15分あたり10リクエスト（無料プラン）
        self.window_duration = 900     # 15分 = 900秒
        self.requests = []
        self.monthly_count = 0
        self.monthly_limit = 10000    # 月間10,000ツイート
        self.month_start = datetime.now()
        self.min_request_interval = 90  # 最小90秒間隔（15分÷10リクエスト）
        self.last_request_time = None
    
    async def wait_if_needed(self):
        """必要に応じて待機"""
        now = datetime.now()
        
        # 最小リクエスト間隔のチェック（90秒）
        if self.last_request_time:
            elapsed = (now - self.last_request_time).total_seconds()
            if elapsed < self.min_request_interval:
                wait_time = self.min_request_interval - elapsed
                logger.info(f"Waiting {wait_time:.1f}s for minimum interval...")
                await asyncio.sleep(wait_time)
                now = datetime.now()
        
        # 月間制限チェック（ツイート数で計算）
        # 1リクエストで5ツイート取得 × 月間リクエスト数
        estimated_monthly_tweets = self.monthly_count * 5
        if estimated_monthly_tweets >= self.monthly_limit:
            logger.error("Monthly tweet limit exceeded! Waiting until next month...")
            return False
        
        # 月間リセット
        if (now - self.month_start).days >= 30:
            self.monthly_count = 0
            self.month_start = now
        
        # 15分間のウィンドウをクリア
        cutoff = now - timedelta(seconds=self.window_duration)
        self.requests = [req_time for req_time in self.requests if req_time > cutoff]
        
        # レート制限チェック（10リクエスト/15分）
        if len(self.requests) >= self.requests_per_window:
            sleep_time = self.window_duration - (now - self.requests[0]).total_seconds()
            if sleep_time > 0:
                logger.warning(f"Rate limit reached (10 req/15min). Waiting {sleep_time:.1f} seconds...")
                await asyncio.sleep(sleep_time)
                return await self.wait_if_needed()
        
        # リクエストを記録
        self.requests.append(now)
        self.monthly_count += 1
        self.last_request_time = now
        logger.info(f"API Request #{self.monthly_count} (≈{estimated_monthly_tweets} tweets/10000 this month)")
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
                        # レート制限に達した場合、より長く待機
                        await asyncio.sleep(300)  # 5分待機
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
    
async def get_user_tweets(self, user_id, username, max_results=5):
    """ユーザーの最新ツイートを取得（画像・メディア対応 + スキップ対応）"""
    if not await rate_limiter.wait_if_needed():
        return []

    url = f"{self.base_url}/users/{user_id}/tweets"
    headers = {"Authorization": f"Bearer {self.bearer_token}"}
    max_results = max(5, min(max_results, 100))

    params = {
        "max_results": max_results,
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
                    skip_until[username] = datetime.utcnow() + timedelta(minutes=15)
                    logger.warning(f"Temporarily skipping {username} for 15 minutes.")
                    await asyncio.sleep(300)
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
        if TARGET_ACCOUNTS[username] is not None:
            logger.info(f"User ID for {username} already initialized: {TARGET_ACCOUNTS[username]}")
            continue
            
        try:
            user_id = await twitter_api.get_user_id(username)
            if user_id:
                TARGET_ACCOUNTS[username] = user_id
                logger.info(f"✅ Initialized user ID for {username}: {user_id}")
            else:
                logger.error(f"❌ Failed to get user ID for {username}")
            
            # ユーザーID取得間の待機時間（レート制限を考慮して待機しない、RateLimiterが管理）
        except Exception as e:
            logger.error(f"Error initializing {username}: {e}")

async def check_and_post_updates():
    """新規ツイートをチェックしてDiscordに送信（複数投稿対応 + スキップ管理）"""
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)
    
    if not channel:
        logger.error(f"Discord channel not found (ID: {CHANNEL_ID})")
        return
    
    bot_member = channel.guild.get_member(bot.user.id)
    if bot_member and not channel.permissions_for(bot_member).send_messages:
        logger.error(f"❌ Bot doesn't have permission to send messages in channel {CHANNEL_ID}")
        return

    logger.info("Checking for new tweets (rate-limited)...")
    
    # 初回のユーザーID取得
    if None in TARGET_ACCOUNTS.values():
        logger.info("Some accounts not initialized, initializing now...")
        await initialize_user_ids()
    
    now = datetime.utcnow()
    active_accounts = {
        k: v for k, v in TARGET_ACCOUNTS.items()
        if v is not None and (k not in skip_until or skip_until[k] <= now)
    }
    logger.info(f"Active accounts: {len(active_accounts)}/{len(TARGET_ACCOUNTS)}")

    for username, user_id in active_accounts.items():
        try:
            logger.info(f"Checking {username} (ID: {user_id})...")
            tweets = await twitter_api.get_user_tweets(user_id, username, max_results=5)
            
            if tweets:
                new_tweets = []

                for tweet in tweets:
                    tweet_id = tweet["id"]
                    if last_tweet_ids[username] is None:
                        new_tweets = [tweets[0]]
                        break
                    elif tweet_id == last_tweet_ids[username]:
                        break
                    else:
                        new_tweets.append(tweet)

                if tweets:
                    last_tweet_ids[username] = tweets[0]["id"]

                for tweet in reversed(new_tweets):
                    logger.info(f"🆕 New tweet found for {username}: {tweet['id']}")
                    try:
                        embed = discord.Embed(
                            description=tweet["text"],
                            color=0x1DA1F2,
                            timestamp=datetime.utcnow()
                        )

                        if tweet.get('media_info'):
                            for media in tweet['media_info']:
                                if media['type'] == 'photo' and 'url' in media:
                                    embed.set_image(url=media['url'])
                                    break
                                elif media['type'] == 'video' and 'preview_image_url' in media:
                                    embed.set_image(url=media['preview_image_url'])
                                    break

                        await channel.send(embed=embed)
                        logger.info(f"✅ Posted update for {username} to Discord")
                        await asyncio.sleep(2)
                    except discord.Forbidden:
                        logger.error("❌ Permission denied: Cannot send messages to this channel")
                        return
                    except Exception as e:
                        logger.error(f"Error posting to Discord: {e}")
            else:
                logger.info(f"No new tweets for {username}")
                
        except Exception as e:
            logger.error(f"Error checking {username}: {e}")


# 定期実行タスク（2時間間隔 - 無料プラン対応）
@tasks.loop(hours=2)  # 2時間間隔
async def periodic_check():
    """2時間ごとに新規ツイートをチェック"""
    await check_and_post_updates()

@periodic_check.before_loop
async def before_periodic_check():
    await bot.wait_until_ready()
    
    # 初期化を遅延実行（レート制限対策）
    logger.info("Waiting 30 seconds before first check to stabilize connection...")
    await asyncio.sleep(30)  # 30秒待機
    
    logger.info("Twitter API bot is ready, starting periodic checks...")

@bot.event
async def on_ready():
    logger.info(f"Bot logged in as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Target channel: {CHANNEL_ID}")
    logger.info(f"Monitoring accounts: {list(TARGET_ACCOUNTS.keys())}")
    
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
    estimated_monthly_tweets = rate_limiter.monthly_count * 5
    remaining_monthly = rate_limiter.monthly_limit - estimated_monthly_tweets
    embed.add_field(
        name="月間使用量",
        value=f"リクエスト数: {rate_limiter.monthly_count}回\n"
              f"推定ツイート数: {estimated_monthly_tweets:,}/{rate_limiter.monthly_limit:,}\n"
              f"残り: {remaining_monthly:,}ツイート",
        inline=False
    )
    
    # 15分間のウィンドウ
    now = datetime.now()
    cutoff = now - timedelta(seconds=900)
    recent_requests = [req for req in rate_limiter.requests if req > cutoff]
    
    embed.add_field(
        name="15分間の使用量",
        value=f"{len(recent_requests)}/10",
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

# 権限チェックコマンド
@bot.command()
async def check_permissions(ctx):
    """Bot権限の確認"""
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        await ctx.send("❌ 指定されたチャンネルが見つかりません。")
        return
    
    bot_member = channel.guild.get_member(bot.user.id)
    if not bot_member:
        await ctx.send("❌ Botがサーバーに参加していません。")
        return
    
    permissions = channel.permissions_for(bot_member)
    
    embed = discord.Embed(title="🔐 Bot権限チェック", color=0x00ff00 if permissions.send_messages else 0xff0000)
    embed.add_field(name="チャンネル", value=f"{channel.mention}", inline=False)
    
    required_perms = {
        "メッセージを送信": permissions.send_messages,
        "埋め込みリンク": permissions.embed_links,
        "メッセージを読む": permissions.read_messages,
        "メッセージ履歴を読む": permissions.read_message_history
    }
    
    for perm_name, has_perm in required_perms.items():
        status = "✅" if has_perm else "❌"
        embed.add_field(name=perm_name, value=status, inline=True)
    
    if not all(required_perms.values()):
        embed.add_field(
            name="⚠️ 権限不足",
            value="Botに必要な権限を付与してください。\n"
                  "サーバー設定 → 連携サービス → Bot → 権限を編集",
            inline=False
        )
    
    await ctx.send(embed=embed)

# 使用量計算表示コマンド
@bot.command()
async def usage(ctx):
    """API使用量の詳細を表示"""
    embed = discord.Embed(title="📊 API使用量分析", color=0x1DA1F2)
    
    # 現在の設定
    check_interval_hours = 2  # 2時間
    accounts = len([v for v in TARGET_ACCOUNTS.values() if v is not None])
    requests_per_check = accounts  # 各アカウント1リクエスト
    tweets_per_request = 5
    
    # 1日の計算
    checks_per_day = 24 / check_interval_hours
    daily_requests = checks_per_day * requests_per_check
    daily_tweets = daily_requests * tweets_per_request
    
    # 1ヶ月の計算
    monthly_requests = daily_requests * 30
    monthly_tweets = daily_tweets * 30
    
    # 制限との比較
    monthly_tweet_limit = 10000
    rate_limit_per_15min = 10
    
    embed.add_field(
        name="⚙️ 現在の設定",
        value=f"チェック間隔: {check_interval_hours}時間\n"
              f"監視アカウント: {accounts}個\n"
              f"1リクエストあたり: {tweets_per_request}ツイート",
        inline=False
    )
    
    embed.add_field(
        name="📅 1日あたり",
        value=f"チェック回数: {checks_per_day:.1f}回\n"
              f"リクエスト数: {daily_requests:.1f}回\n"
              f"ツイート取得数: {daily_tweets:.1f}件",
        inline=True
    )
    
    embed.add_field(
        name="📆 1ヶ月あたり",
        value=f"リクエスト数: {monthly_requests:.0f}回\n"
              f"ツイート取得数: {monthly_tweets:.0f}件\n"
              f"制限使用率: {(monthly_tweets/monthly_tweet_limit)*100:.1f}%",
        inline=True
    )
    
    embed.add_field(
        name="✅ 無料プラン制限",
        value=f"15分あたり: {rate_limit_per_15min}リクエスト\n"
              f"月間ツイート: {monthly_tweet_limit:,}件\n"
              f"**現在の設定は制限内です**" if monthly_tweets < monthly_tweet_limit else "**⚠️ 制限超過の恐れ**",
        inline=False
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
    embed.add_field(name="チェック間隔", value="2時間", inline=True)
    embed.add_field(name="レート制限", value="10回/15分", inline=True)
    embed.add_field(name="月間制限", value="10,000ツイート", inline=True)
    embed.add_field(name="監視アカウント数", value=f"{len(TARGET_ACCOUNTS)}個", inline=True)
    embed.add_field(name="API バージョン", value="Twitter API v2", inline=True)
    embed.add_field(name="プラン", value="Basic (無料)", inline=True)
    embed.add_field(name="サービス", value="Background Worker", inline=True)
    embed.add_field(name="機能", value="ツイート本文 + 画像対応", inline=True)
    embed.add_field(name="複数投稿", value="対応済み", inline=True)
    
    await ctx.send(embed=embed)

if __name__ == '__main__':
    logger.info("=== Starting Twitter API Discord Bot ===")
    logger.info(f"Monitoring accounts: {list(TARGET_ACCOUNTS.keys())}")
    logger.info(f"Target channel ID: {CHANNEL_ID}")
    logger.info("Using Twitter API v2 Basic (Free) plan limits")
    logger.info("Rate limit: 10 requests per 15 minutes")
    logger.info("Check interval: 2 hours")
    
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        exit(1)
