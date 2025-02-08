import os
import yt_dlp
import asyncio
import threading
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Write the cookies from the environment variable to a file
cookies_content = os.getenv("YOUTUBE_COOKIES")
if cookies_content:
    with open("cookies.txt", "w") as f:
        f.write(cookies_content)

# Telegram Bot Credentials
API_ID = "18073399"
API_HASH = "1a13234f38fc517092f1af85f1e74e40"
BOT_TOKEN = "7732610185:AAGKCuF7GYT-YUMEmbckRGX-5UQU278FyDg"

app = Client("yt_downloader_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Directory to store downloads
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Active downloads dictionary
active_downloads = {}

# Store user choices temporarily
user_choices = {}

# Start command
@app.on_message(filters.command("start"))
async def start(bot, message):
    await message.reply_text("Send me a YouTube link or playlist, and I'll download it for you!")

# Handle YouTube links & playlists
@app.on_message(filters.regex(r"https?://(www\.)?(youtube\.com|youtu\.be)/.+"))
async def youtube_link(bot, message):
    url = message.text
    user_choices[message.chat.id] = {"url": url}

    # Check if the URL is a playlist
    if "playlist" in url:
        await fetch_playlist_info(bot, message, url)
    else:
        # Ask for format selection
        buttons = [
            [InlineKeyboardButton("🎥 MP4 (Video)", callback_data="choose_video")],
            [InlineKeyboardButton("🎵 MP3 (Audio)", callback_data="choose_audio")]
        ]
        await message.reply_text("Choose a format:", reply_markup=InlineKeyboardMarkup(buttons))

# Fetch playlist information
async def fetch_playlist_info(bot, message, url):
    await message.reply_text("Fetching playlist details...")

    ydl_opts = {"quiet": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        videos = info.get("entries", [])

    if not videos:
        await message.reply_text("No videos found in this playlist.")
        return

    user_choices[message.chat.id]["playlist_videos"] = videos

    buttons = [
        [InlineKeyboardButton("Download All", callback_data="playlist_all")],
        *[[InlineKeyboardButton(f"{i+1}. {v['title']}", callback_data=f"playlist_{i}")]
          for i, v in enumerate(videos[:5])]  # Show first 5 options
    ]
    await message.reply_text("Select videos to download:", reply_markup=InlineKeyboardMarkup(buttons))

# Handle playlist selection
@app.on_callback_query(filters.regex("playlist_"))
async def playlist_selection(bot, query):
    chat_id = query.message.chat.id
    videos = user_choices[chat_id]["playlist_videos"]

    if query.data == "playlist_all":
        await query.message.edit_text("Downloading entire playlist...")
        threading.Thread(target=lambda: asyncio.run(download_playlist(bot, chat_id, videos))).start()
    else:
        index = int(query.data.split("_")[1])
        await query.message.edit_text(f"Downloading: {videos[index]['title']}")
        threading.Thread(target=lambda: asyncio.run(download_video_or_audio(bot, chat_id, videos[index]['webpage_url'], "video"))).start()

# Pause or cancel downloads
@app.on_message(filters.command(["pause", "cancel"]))
async def pause_cancel(bot, message):
    chat_id = message.chat.id
    if chat_id in active_downloads:
        active_downloads[chat_id]["paused"] = True
        await message.reply_text("Download paused! Use /resume to continue." if message.text == "/pause" else "Download canceled!")
    else:
        await message.reply_text("No active downloads found.")

# Resume downloads
@app.on_message(filters.command("resume"))
async def resume(bot, message):
    chat_id = message.chat.id
    if chat_id in active_downloads and active_downloads[chat_id]["paused"]:
        active_downloads[chat_id]["paused"] = False
        await message.reply_text("Resuming download...")
        threading.Thread(target=lambda: asyncio.run(download_video_or_audio(bot, chat_id, active_downloads[chat_id]["url"], active_downloads[chat_id]["format"]))).start()
    else:
        await message.reply_text("No paused downloads found.")

# Download entire playlist
async def download_playlist(bot, chat_id, videos):
    for video in videos:
        await download_video_or_audio(bot, chat_id, video["webpage_url"], "video")

# Function to show a progress bar
async def progress_hook(d, message, chat_id):
    if chat_id in active_downloads and active_downloads[chat_id]["paused"]:
        return  # Pause download
    if d["status"] == "downloading":
        percent = d["_percent_str"].strip()
        await message.edit_text(f"Downloading... {percent}")
    elif d["status"] == "finished":
        await message.edit_text("Download complete! Uploading...")

# Handle format selection
@app.on_callback_query()
async def format_selection(bot, query):
    chat_id = query.message.chat.id
    url = user_choices[chat_id]["url"]
    format_type = "audio" if query.data == "choose_audio" else "video"

    active_downloads[chat_id] = {"url": url, "format": format_type, "paused": False}
    threading.Thread(target=lambda: asyncio.run(download_video_or_audio(bot, chat_id, url, format_type))).start()

async def download_video_or_audio(bot, chat_id, url, format_type):
    filename = f"{DOWNLOAD_DIR}/output.{'mp3' if format_type == 'audio' else 'mp4'}"
    
        ydl_opts = {
        "outtmpl": filename,
        "format": "bestaudio" if format_type == "audio" else "best",
        "cookies": "cookies.txt",  # ✅ Use the cookies file
        "progress_hooks": [lambda d: app.loop.create_task(progress_hook(d, bot.get_messages(chat_id, bot.get_history(chat_id)[0].message_id), chat_id))],
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}] if format_type == "audio" else [],
    }


    await bot.send_message(chat_id, "Downloading... 0%")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if format_type == "video":
            await bot.send_video(chat_id, video=filename, caption="Here is your video! 🎥")
        else:
            await bot.send_audio(chat_id, audio=filename, caption="Here is your audio! 🎵")

        os.remove(filename)
        del active_downloads[chat_id]

    except Exception as e:
        await bot.send_message(chat_id, f"Error: {str(e)}")
        del active_downloads[chat_id]

# Run the bot
app.run()
