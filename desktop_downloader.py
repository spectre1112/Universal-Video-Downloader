import sys, os, threading, subprocess, ctypes, traceback
import socket
import urllib.parse
import yt_dlp
import keyboard
import pyperclip
import time
import pyautogui
import win32api
import win32gui
import win32con
from pytubefix import YouTube
from pytubefix import request as pytubefix_request
from yt_dlp.networking.impersonate import ImpersonateTarget

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QLineEdit, QPushButton, QComboBox, QLabel, 
                             QProgressBar, QFrame, QHBoxLayout, QSystemTrayIcon, QMenu)
from PySide6.QtCore import Qt, Signal, Slot, QPoint, QTimer
from PySide6.QtGui import QIcon

def _try_bring_to_front():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(b"show", ("127.0.0.1", 47892))
        s.close()
    except:
        pass
    os._exit(0)

_lock_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    _lock_socket.bind(("127.0.0.1", 47892))
except OSError:
    _try_bring_to_front()
try:
    myappid = 'video.downloader.pro.v4.2' 
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

pytubefix_request.default_range_size = 4194304 

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def open_or_activate_explorer(target_path):
    target_path = os.path.normpath(target_path)
    is_file = os.path.isfile(target_path)
    folder_path = os.path.dirname(target_path) if is_file else target_path

    try:
        import win32com.client
        import win32gui
        import win32con
      
        shell = win32com.client.Dispatch("Shell.Application")
        for window in shell.Windows():
            if window.FullName and "explorer.exe" in window.FullName.lower():
                raw_url = window.LocationURL.replace("file:///", "").replace("/", "\\")
                open_path = urllib.parse.unquote(raw_url)
                
                if open_path.lower() == folder_path.lower():
                    hwnd = window.HWND
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)
                    if is_file:
                        try:
                            item = window.Document.Folder.ParseName(os.path.basename(target_path))
                            if item: window.Document.SelectItem(item, 29)
                        except: pass
                    return 
    except Exception:
        pass
        
    if is_file:
        subprocess.Popen(f'explorer /select,"{target_path}"')
    else:
        subprocess.Popen(f'explorer "{folder_path}"')

class DownloaderWorker(threading.Thread):
    def __init__(self, url, type_idx, quality_idx, callback_status, callback_progress, callback_finish):
        super().__init__()
        self.url = url
        self.type_idx = type_idx 
        self.quality_idx = quality_idx 
        self.callback_status = callback_status
        self.callback_progress = callback_progress
        self.callback_finish = callback_finish
        self.downloads_dir = os.path.join(os.path.expanduser('~'), 'Downloads')

    def progress_callback(self, stream, chunk, bytes_remaining):
        total_size = stream.filesize
        percent = int(((total_size - bytes_remaining) / total_size) * 100)
        self.callback_progress.emit(percent)

    def progress_hook_ytdlp(self, d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            if total > 0:
                percent = int((d.get('downloaded_bytes', 0) / total) * 100)
                self.callback_progress.emit(percent)

    def run(self):
        try:
            low_url = self.url.lower()
            if 'youtube.com' in low_url or 'youtu.be' in low_url:
                self.download_youtube()
            else:
                self.download_generic()
        except Exception as e:
            print(f"ERROR: {e}")
            traceback.print_exc()
            self.callback_status.emit("❌ DOWNLOAD ERROR", "#ff6b6b")
        finally:
            self.callback_finish.emit()

    def download_youtube(self):
        self.callback_status.emit("⚡ ANALYZING LINK...", "#60cdff")
        yt = YouTube(self.url, on_progress_callback=self.progress_callback)
        
        res_list = ["2160p", "1080p", "720p"]
        target_res = res_list[self.quality_idx]

        if self.type_idx == 1:
            stream = yt.streams.get_audio_only()
            out_file = stream.download(output_path=self.downloads_dir)
            base, _ = os.path.splitext(out_file)
            final_path = base + ".mp3"
            subprocess.run([resource_path("ffmpeg.exe"), "-y", "-i", out_file, final_path], creationflags=0x08000000)
            if os.path.exists(out_file): os.remove(out_file)
        elif self.type_idx == 2:
            v_stream = yt.streams.filter(res=target_res).first() or yt.streams.get_highest_resolution()
            self.callback_status.emit(f"🎬 DOWNLOADING {v_stream.resolution}...", "#60cdff")
            final_path = v_stream.download(output_path=self.downloads_dir)
        else:
            v_stream = yt.streams.filter(res=target_res).first() or yt.streams.get_highest_resolution()
            a_stream = yt.streams.get_audio_only()
            self.callback_status.emit(f"🎬 DOWNLOADING {v_stream.resolution}...", "#60cdff")
            v_file = v_stream.download(output_path=self.downloads_dir, filename_prefix="v_temp_")
            a_file = a_stream.download(output_path=self.downloads_dir, filename_prefix="a_temp_")
            self.callback_status.emit("🔧 MERGING FILES...", "#ffd700")
            final_path = os.path.join(self.downloads_dir, f"{yt.title}.mp4")
            subprocess.run([resource_path("ffmpeg.exe"), "-y", "-i", v_file, "-i", a_file, "-c", "copy", final_path], creationflags=0x08000000)
            if os.path.exists(v_file): os.remove(v_file)
            if os.path.exists(a_file): os.remove(a_file)

        self.callback_status.emit("✅ COMPLETED", "#60cdff")
        open_or_activate_explorer(final_path)

    def download_generic(self):
        """Generic downloader for TikTok, Instagram, etc."""
        self.callback_status.emit("🌍 ANALYZING...", "#60cdff")
        res = [2160, 1080, 720][self.quality_idx]
        ydl_opts = {
            'outtmpl': os.path.join(self.downloads_dir, '%(title)s.%(ext)s'),
            'progress_hooks': [self.progress_hook_ytdlp],
            'ffmpeg_location': resource_path('ffmpeg.exe'),
            'impersonate': ImpersonateTarget(client='chrome'),
            'format': f'bestvideo[height<={res}]+bestaudio/best',
            'merge_output_format': 'mp4',
            'quiet': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            self.callback_status.emit("📡 DOWNLOADING...", "#60cdff")
            info = ydl.extract_info(self.url, download=True)
            path = ydl.prepare_filename(info)
            open_or_activate_explorer(path)
        self.callback_status.emit("✅ COMPLETED", "#60cdff")

class NativeVideoDownloader(QMainWindow):
    status_signal = Signal(str, str)
    show_signal = Signal()
    progress_signal = Signal(int)
    finish_signal = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon(resource_path("icon.png")))
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(460, 560) 

        self.bg_frame = QFrame(self)
        self.bg_frame.setGeometry(0, 0, 460, 560)
        self.bg_frame.setObjectName("MainFrame")
        
        layout = QVBoxLayout(self.bg_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(35)
        t_lay = QHBoxLayout(self.title_bar)
        t_lay.setContentsMargins(15, 0, 0, 0)
        lbl = QLabel("Universal Downloader Pro v4.2")
        lbl.setStyleSheet("color: #757575; font-size: 10px; font-weight: 800; border: none;")
        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(45, 35)
        self.btn_close.setObjectName("CloseBtn")
        self.btn_close.clicked.connect(self.close)
        t_lay.addWidget(lbl)
        t_lay.addStretch()
        t_lay.addWidget(self.btn_close)

        self.container = QWidget()
        c_lay = QVBoxLayout(self.container)
        c_lay.setContentsMargins(40, 15, 40, 35)
        c_lay.setSpacing(12)

        self.header = QLabel("Universal Video\nDownloader")
        self.header.setStyleSheet("color: white; font-size: 30px; font-weight: 700; border: none;")
        self.header.setAlignment(Qt.AlignCenter)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste link here...")
        self.url_input.setMinimumHeight(48)

        self.type_box = QComboBox()
        self.type_box.addItems(["🎬   MP4 (Video + Audio)", "🎵   MP3 (Audio Only)", "🔇   MP4 (No Audio)"])
        self.type_box.setMinimumHeight(45)

        self.quality_box = QComboBox()
        self.quality_box.addItems(["🔥   4K / Max", "🎞️   1080p / Full HD", "📺   720p / HD"])
        self.quality_box.setMinimumHeight(45)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setValue(0)
        self.progress.hide()

        self.dl_btn = QPushButton("DOWNLOAD")
        self.dl_btn.setObjectName("DownloadBtn")
        self.dl_btn.setMinimumHeight(60)
        self.dl_btn.clicked.connect(self.start_download)

        self.status = QLabel("Ready to work")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setObjectName("StatusLabel")

        c_lay.addWidget(self.header)
        c_lay.addWidget(self.url_input)
        c_lay.addWidget(self.type_box)
        c_lay.addWidget(self.quality_box)
        c_lay.addWidget(self.progress)
        c_lay.addWidget(self.dl_btn)
        c_lay.addWidget(self.status)

        layout.addWidget(self.title_bar)
        layout.addWidget(self.container)

        self.apply_styles()
        
        self.status_signal.connect(self.update_status)
        self.progress_signal.connect(self.update_progress)
        self.finish_signal.connect(self.on_dl_finish)
        self.old_pos = None
        self.tray = QSystemTrayIcon(QIcon(resource_path("icon.png")), self)
        tray_menu = QMenu()
        tray_menu.addAction("Open", self.show)
        tray_menu.addAction("Exit", QApplication.instance().quit)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(lambda r: self.show() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()
        self.show_signal.connect(self._bring_to_front)
        self._start_ipc_listener()
        keyboard.add_hotkey('ctrl+shift+s', self.hotkey_download)

    def _start_ipc_listener(self):
        """Listen for single instance show command"""
        def listen():
            _lock_socket.settimeout(1.0)
            while True:
                try:
                    data, _ = _lock_socket.recvfrom(16)
                    if data == b"show":
                        self.show_signal.emit()
                except socket.timeout:
                    continue
                except:
                    break
        threading.Thread(target=listen, daemon=True).start()

    def _bring_to_front(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def apply_styles(self):
        """Interface styling via QSS"""
        self.setStyleSheet("""
            #MainFrame { background-color: #1c1c1c; border: 1px solid #333333; border-radius: 12px; }
            #CloseBtn { background: transparent; color: #888; border: none; font-size: 12px; }
            #CloseBtn:hover { background: #e81123; color: white; border-top-right-radius: 11px; }
            QLineEdit, QComboBox {
                background-color: #2b2b2b; color: #ffffff; border: 1px solid #3d3d3d;
                border-bottom: 2px solid #0078d4; border-radius: 6px; padding-left: 15px;
            }
            QComboBox::drop-down { border: none; width: 0px; }
            QComboBox QAbstractItemView {
                background-color: #2b2b2b; color: white; border: 1px solid #333;
                selection-background-color: #0078d4; outline: none;
            }
            QProgressBar { background-color: #2b2b2b; border: none; border-radius: 3px; }
            QProgressBar::chunk { background-color: #0078d4; border-radius: 3px; }
            #DownloadBtn {
                background-color: #0078d4; color: white; border-radius: 8px;
                font-weight: bold; font-size: 16px; border-bottom: 4px solid #005a9e;
            }
            #DownloadBtn:hover { background-color: #0086ed; }
            #StatusLabel { 
                color: #606060; 
                font-size: 13px; 
                border: none; 
                margin-top: 5px; 
            }
        """)

    def update_progress(self, val):
        self.progress.show()
        self.progress.setValue(val)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton: self.old_pos = event.globalPosition().toPoint()
    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = QPoint(event.globalPosition().toPoint() - self.old_pos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def start_download(self):
        """Collect UI data and start background thread"""
        url = self.url_input.text().strip()
        if not url: return
        self.dl_btn.setEnabled(False)
        self.progress.setValue(0)
        DownloaderWorker(url, self.type_box.currentIndex(), self.quality_box.currentIndex(), 
                         self.status_signal, self.progress_signal, self.finish_signal).start()
    
    def hotkey_download(self):
        """Automated hotkey logic for copying URL and starting download"""
        def _do():
            time.sleep(0.5)
            win32api.keybd_event(0x11, 0, 0, 0)
            win32api.keybd_event(0x4C, 0, 0, 0)
            win32api.keybd_event(0x4C, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(0x11, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.4)
            win32api.keybd_event(0x11, 0, 0, 0)
            win32api.keybd_event(0x43, 0, 0, 0)
            win32api.keybd_event(0x43, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(0x11, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.4)
            url = pyperclip.paste().strip()
            if url.startswith('http'):
                self.url_input.setText(url)
                self.start_download()
        threading.Thread(target=_do).start()

    @Slot(str, str)
    def update_status(self, text, color):
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color}; font-size: 13px; border: none; margin-top: 5px;")

    @Slot()
    def on_dl_finish(self):
        """Unlock button and reset status after completion"""
        self.dl_btn.setEnabled(True)
        self.progress.hide()
        QTimer.singleShot(2000, lambda: self.update_status("Ready to work", "#606060"))

    def closeEvent(self, event):
        """Minimize to tray instead of closing"""
        event.ignore()
        self.hide()
        self.tray.showMessage("Universal Downloader", "App minimized to tray", QSystemTrayIcon.MessageIcon.Information, 2000)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = NativeVideoDownloader()
    window.show()

    sys.exit(app.exec())
