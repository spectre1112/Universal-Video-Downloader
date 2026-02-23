import os
import asyncio
import subprocess
import time
import shutil
import re
import traceback
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.telegram import TelegramAPIServer
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import InputMediaPhoto, FSInputFile
from pytubefix import YouTube
from pytubefix import request as pytubefix_request
import yt_dlp

# --- Configuration ---
# Use environment variables or a .env file for security
API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
FFMPEG_PATH = 'ffmpeg' 
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, 'downloads')
# Relative path to gallery-dl within venv
GALLERY_DL_PATH = os.path.join(BASE_DIR, 'venv', 'bin', 'gallery-dl')
TG_LIMIT_MB = 2000  # 2 GB Telegram limit

pytubefix_request.default_range_size = 10485760 

# Local API Server setup
local_server = TelegramAPIServer.from_base("http://localhost:8081")
session = AiohttpSession(api=local_server)
bot = Bot(token=API_TOKEN, session=session)
dp = Dispatcher()

# --- Utilities ---
def format_size(bytes):
    if bytes is None or bytes == 0: return "0MB"
    return f"{bytes / 1024 / 1024:.1f}MB"

def get_status_text(pct, downloaded=None, total=None):
    length = 10
    filled = int(length * pct // 100)
    bar = '█' * filled + '░' * (length - filled)
    status = f"⏳ Downloading: |{bar}| {pct}%"
    if downloaded is not None and total is not None:
        status += f"\n📦 {format_size(downloaded)} / {format_size(total)}"
    return status

def is_url(text):
    return re.match(r'^https?://', text) is not None

# --- TikTok Album Downloader ---
async def download_photo_album(message, url, status_msg):
    task_id = f"photo_{int(time.time())}"
    task_dir = os.path.join(DOWNLOAD_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)

    try:
        # Launch gallery-dl
        cmd = [GALLERY_DL_PATH, "--directory", task_dir, "--no-mtime", url]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        # Progress simulation based on stdout
        count = 0
        while not process.stdout.at_eof():
            line = await process.stdout.readline()
            if line:
                count += 1
                pct = min(count * 100, 100)
                try: await status_msg.edit_text(get_status_text(pct))
                except: pass

        await process.wait()

        media_photos = []
        audio_file = None

        # Collect files recursively
        for root, dirs, files in os.walk(task_dir):
            for f in sorted(files):
                path = os.path.join(root, f)
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    media_photos.append(InputMediaPhoto(media=FSInputFile(path)))
                elif f.lower().endswith(('.mp3', '.m4a', '.wav')):
                    audio_file = path

        if media_photos:
            # Send photos in groups of 10
            for i in range(0, len(media_photos), 10):
                await bot.send_media_group(message.chat.id, media=media_photos[i:i+10])
            # Send associated audio
            if audio_file:
                await bot.send_audio(message.chat.id, audio=FSInputFile(audio_file))
            await status_msg.delete()
        else:
            await status_msg.edit_text("❌ Album not found or empty.")

    except Exception:
        await status_msg.edit_text("⚠️ An error occurred during processing.")
    finally:
        shutil.rmtree(task_dir, ignore_errors=True)

# --- YouTube Downloader ---
async def download_yt_video(url, res, status_msg, title):
    loop = asyncio.get_running_loop()
    last_edit_time = 0

    async def safe_edit(text):
        try: await status_msg.edit_text(text)
        except: pass

    def on_progress(stream, chunk, bytes_remaining):
        nonlocal last_edit_time
        total = stream.filesize
        downloaded = total - bytes_remaining
        pct = int(downloaded / total * 100)
        current_time = time.time()
        if current_time - last_edit_time > 1.5 or pct == 100:
            last_edit_time = current_time
            asyncio.run_coroutine_threadsafe(safe_edit(get_status_text(pct, downloaded, total)), loop)

    yt = YouTube(url, on_progress_callback=on_progress)
    v_stream = yt.streams.filter(res=res).first()
    a_stream = yt.streams.get_audio_only()

    # Size validation
    total_size = v_stream.filesize + (a_stream.filesize if a_stream else 0)
    if total_size / 1024 / 1024 > TG_LIMIT_MB:
        await status_msg.edit_text(f"⚠️ File is too large ({format_size(total_size)}). Limit: 2GB.")
        return None

    v_path = await asyncio.to_thread(v_stream.download, output_path=DOWNLOAD_DIR, filename_prefix="v_")
    a_path = await asyncio.to_thread(a_stream.download, output_path=DOWNLOAD_DIR, filename_prefix="a_")
    
    final_filename = f"{title}.mp4".replace("/", "_").replace(" ", "_")
    final_path = os.path.join(DOWNLOAD_DIR, final_filename)
    
    cmd = [FFMPEG_PATH, "-y", "-i", v_path, "-i", a_path, "-c", "copy", final_path]
    await asyncio.to_thread(subprocess.run, cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if os.path.exists(v_path): os.remove(v_path)
    if os.path.exists(a_path): os.remove(a_path)
    return final_path

# --- Generic Video Downloader (TikTok/Insta/etc) ---
async def download_generic(message, url, status_msg):
    loop = asyncio.get_running_loop()
    last_edit_time = 0

    async def safe_edit(text):
        try: await status_msg.edit_text(text)
        except: pass

    def progress_hook(d):
        nonlocal last_edit_time
        if d['status'] == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            if total > 0:
                pct = int(downloaded / total * 100)
                current_time = time.time()
                if current_time - last_edit_time > 1.5 or pct == 100:
                    last_edit_time = current_time
                    asyncio.run_coroutine_threadsafe(safe_edit(get_status_text(pct, downloaded, total)), loop)

    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
        'quiet': True,
        'progress_hooks': [progress_hook],
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=True)
            path = ydl.prepare_filename(info)
            if os.path.exists(path):
                size_mb = os.path.getsize(path) / 1024 / 1024
                if size_mb > TG_LIMIT_MB:
                    await message.answer(f"⚠️ Video is too heavy ({size_mb:.1f} MB).")
                else:
                    await bot.send_video(message.chat.id, video=FSInputFile(path))
                os.remove(path)
            await status_msg.delete()
    except Exception:
        try: await status_msg.delete()
        except: pass

# --- Handlers ---
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Hello! Send me a link from YouTube, TikTok, or Instagram.")

@dp.message()
async def handle_link(message: types.Message):
    url = message.text
    if not is_url(url): return

    # TikTok Photo Album interception
    if "tiktok.com" in url and "/photo/" in url:
        status = await message.answer(get_status_text(0))
        await download_photo_album(message, url, status)
        return

    # YouTube processing
    if "youtube.com" in url or "youtu.be" in url:
        status_msg = await message.answer("⏳ Analyzing...")
        try:
            yt = YouTube(url)
            a_stream = yt.streams.get_audio_only()
            builder = InlineKeyboardBuilder()
            # Supporting 4K and 2K
            for res in ['2160p', '1440p', '1080p', '720p', '480p', '360p']:
                s = yt.streams.filter(res=res).first()
                if s:
                    total_size = s.filesize + (a_stream.filesize if a_stream else 0)
                    builder.button(text=f"🎬 {res} ({format_size(total_size)})", callback_data=f"dl_yt|{res}|{url}")
            builder.adjust(1)
            await status_msg.edit_text(f"🎥 {yt.title}", reply_markup=builder.as_markup())
        except:
            try: await status_msg.delete()
            except: pass
    else:
        status = await message.answer(get_status_text(0))
        await download_generic(message, url, status)

@dp.callback_query(F.data.startswith("dl_yt|"))
async def callback_dl_yt(callback: types.CallbackQuery):
    _, res, url = callback.data.split("|")
    await callback.answer()
    await callback.message.delete()
    status_msg = await callback.message.answer(get_status_text(0))
    try:
        yt = YouTube(url)
        path = await download_yt_video(url, res, status_msg, yt.title)
        if path and os.path.exists(path):
            await bot.send_video(callback.message.chat.id, video=FSInputFile(path))
            os.remove(path)
            await status_msg.delete()
    except:
        try: await status_msg.delete()
        except: pass

async def main():
    # Clean downloads directory on startup
    if os.path.exists(DOWNLOAD_DIR):
        shutil.rmtree(DOWNLOAD_DIR)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())