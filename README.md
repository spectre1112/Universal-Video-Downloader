# Universal Video Downloader

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows-0078d7.svg)
![License](https://img.shields.io/badge/license-Unlicense-blue.svg)

A powerful media downloader package written in Python. This project includes a modern Windows GUI built with **pywebview + HTML/CSS/JS** 

## 📦 Components

### 💻 Desktop GUI (main.py)
A modern Windows application with a dark-themed web-based interface.
* **Quality:** Supports resolution up to 2160p (4K).
* **Queue:** Download multiple videos sequentially with a live progress UI.
* **Hotkey:** Global `Ctrl+Shift+S` pastes the current clipboard URL and adds it to the queue.
* **Tray:** Minimises to the system tray; close button hides the window.
* **Preview:** Fetches video metadata (title, thumbnail, duration) before downloading.

### Project structure
```
Universal-Video-Downloader/
├── main.py                    # Entry point: pywebview window + single-instance guard
├── core/
│   ├── api.py                 # JS↔Python bridge (pywebview API class)
│   ├── downloader.py          # yt-dlp + pytubefix download logic
│   ├── queue_manager.py       # Sequential download queue
│   └── utils.py               # resource_path, open_explorer, logging
├── ui/
│   ├── index.html             # App shell with tabs
│   ├── style.css              # Dark theme with animations
│   └── app.js                 # Queue polling, tab logic, JS API calls
├── requirements.txt
```

## 🛠 Setup & Build

### 1. Installation
Install all dependencies:
```
pip install -r requirements.txt
```

For the Telegram Bot only:
```
pip install aiogram pytubefix yt-dlp gallery-dl
```

### 2. FFmpeg Setup
FFmpeg is required to merge audio and video streams.
* **Direct Download:** https://github.com/GyanD/codexffmpeg/releases/
* **Note:** Place `ffmpeg.exe` in the project root or add its `bin` folder to the system PATH.

### 3. Node.js Setup (required for YouTube)
Since yt-dlp 2025.11.12, YouTube extraction requires a JavaScript runtime. Run the provided script to download a portable Node.js binary:
```
python setup_node.py
```
This places `node/node.exe` in the project root. The downloader will detect it automatically.

### 4. Running
```
python main.py
```

### 5. PyInstaller Build (Windows)
Ensure `ffmpeg.exe`, `icon.png`, `icon.ico`, the `ui/` folder, and the `node/` folder (from `setup_node.py`) are present before building:

```
python -m PyInstaller --onefile --windowed --icon=icon.ico ^
  --add-data "ffmpeg.exe;." ^
  --add-data "icon.png;." ^
  --add-data "icon.ico;." ^
  --add-data "ui;ui" ^
  --add-data "node;node" ^
  main.py
```

## ⚠️ Requirements

* **FFmpeg:** Essential for stream merging.
* **yt-dlp:** Primary engine for generic video extraction.
* **pytubefix:** Secondary engine optimised for YouTube.
* **pywebview ≥ 5.0:** Renders the HTML/JS UI inside a native window.
* **filelock:** Single-instance guard (replaces the old UDP socket approach).
* **pystray + Pillow:** System tray icon.
* **keyboard:** Global hotkey registration.
