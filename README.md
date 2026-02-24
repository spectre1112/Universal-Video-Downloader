# Universal Video Downloader

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Platform](https://img.shields.io/badge/platform-windows%20%7C%20telegram-lightgrey.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

A powerful media downloader package written in Python. This project includes a Windows-optimized graphical user interface and a Telegram bot designed to handle large amounts of data via the local Telegram API.

## 📦 Components

### 💻 Desktop GUI (desktop_downloader.py)
A dedicated Windows application that provides high-quality background data processing.
* **Quality:** Supports resolution up to 2160p (4K) at 60 fps.
* **Workflow:** Use the global hook `Ctrl+Shift+S` to copy a link from the active browser page
* **System Integration:** Supports hiding in the system tray

### 🤖 Telegram Bot (telegram_bot.py)
A backend bot built for the local Telegram API server.
* **YouTube Support:** Includes interactive resolution selection for end-users.
* **Extended Limits:** Supports file uploads up to 2GB (requires Local API).

## 🛠 Setup & Build

### 1. Installation
Install the required dependencies from the provided requirement files:

##### For Desktop Client (includes yt-dlp, pytubefix)
```
pip install -r requirements_app.txt
```
##### For Telegram Bot (includes yt-dlp, pytubefix, gallery-dl)
```
pip install -r requirements_bot.txt
```
### 2. FFmpeg Setup
FFmpeg is required to merge audio and video into one stream.
* **Direct Download:** https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-7.1.1-essentials_build.zip
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
* **gallery-dl:** Required for TikTok photos processing on the bot side.
* **Local API:** The bot requires a local server instance to bypass the standard 50MB upload limit.
