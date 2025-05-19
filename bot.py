import requests
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks, commands

TOKEN = 'YOUR_DISCORD_BOT_TOKEN'
CHANNEL_ID = 1234567890  # 投稿先チャンネルID
NITTER_URL = 'https://nitter.poast.org/Crypto_AI_chan_'

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

last_post = None  # 最後の投稿URLなどを記憶

@tasks.loop(minutes=60)  # 1時間ごとにチェック
async def check_nitter():
    global last_post
    res = requests.get(NITTER_URL)
    soup = BeautifulSoup(res.text, 'html.parser')
    tweets = soup.select('.timeline-item')

    if tweets:
        first = tweets[0]
        link = 'https://twitter.com' + first.select_one('a.tweet-link')['href']
        content = first.select_one('.tweet-content').text.strip()

        if link != last_post:
            last_post = link
            channel = bot.get_channel(CHANNEL_ID)
            await channel.send(f"📝 新しい投稿がありました！\n{content}\n{link}")

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    check_nitter.start()

bot.run(TOKEN)
