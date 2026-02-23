# Universal Video Downloader

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Platform](https://img.shields.io/badge/platform-windows%20%7C%20telegram-lightgrey.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

A powerful Python media downloading suite. This project features a Windows-optimized Desktop GUI and a Telegram Bot designed for high-capacity usage via Local Telegram API.

## 📦 Components

### 💻 Desktop GUI (desktop_downloader.py)
A dedicated Windows application for high-quality background processing.
* **Quality:** Supports resolutions up to 2160p (4K) at 60FPS.
* **Workflow:** Uses a `Ctrl+Shift+S` global hook for instant clipboard processing and automated downloads.
* **System Integration:** Runs in the system tray with background execution capabilities via Win32 API.

### 🤖 Telegram Bot (telegram_bot.py)
A backend bot optimized for the Local Telegram API Server.
* **TikTok Integration:** Features automated photo album scraping.
* **YouTube Support:** Includes interactive resolution selection for end-users.
* **Extended Limits:** Supports file uploads up to 2GB (requires Local API).

## 🛠 Setup & Build

### 1. Installation
Install the required dependencies from the provided requirement files:

##### For Desktop Client (includes yt-dlp, pytubefix)
```
pip install -r requirements_app.txt
```
##### For Telegram Bot (includes gallery-dl)
```
pip install -r requirements_bot.txt
```
### 2. FFmpeg Setup
FFmpeg is essential for stream merging.
* **Direct Download:** https://www.ffmpeg.org/download.html#build-windows
* **Repository:** ```git clone https://git.ffmpeg.org/ffmpeg.git ffmpeg```
* **Note:** Place `ffmpeg.exe` in the project root or add its `bin` folder to your System PATH.

### 3. PyInstaller Build (Windows)
Ensure `ffmpeg.exe`, `icon.png`, and `icon.ico` are present in the root directory before building:

```
python -m PyInstaller --onefile --windowed --icon=icon.ico --add-data "ffmpeg.exe;." --add-data "icon.png;." --add-data "icon.ico;." desktop_downloader.py
```

## ⚠️ Requirements

* **FFmpeg:** Essential for stream merging.
* **yt-dlp:** Primary engine for video extraction.
* **pytubefix:** Secondary engine for YouTube processing.
* **gallery-dl:** Required for TikTok photo album processing on the bot side.
* **Local API:** The bot requires a local server instance to bypass the standard 50MB upload limit.
