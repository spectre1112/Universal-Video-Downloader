import sys
import os
import threading
import logging

import webview
import pyperclip
import keyboard
from filelock import FileLock, Timeout

from core.utils import setup_logging, resource_path, set_app_user_model_id
from core.api import Api
from core.queue_manager import QueueManager

logger = logging.getLogger(__name__)

_LOCK_FILE = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "universal_video_downloader.lock")

# ---------------------------------------------------------------------------
#                         Tray icon (pystray + Pillow)
# ---------------------------------------------------------------------------


def _build_tray(window):
    try:
        import pystray
        from PIL import Image
        icon_path = resource_path("icon.png")
        image = Image.open(icon_path)

        def _show(_icon, _item):
            window.show()

        def _quit(_icon, _item):
            _icon.stop()
            window.destroy()

        menu = pystray.Menu(
            pystray.MenuItem("Open", _show, default=True),
            pystray.MenuItem("Quit", _quit),
        )
        tray = pystray.Icon("Universal Video Downloader", image, "Universal Video Downloader", menu)

        def _run_tray():
            tray.run()

        threading.Thread(target=_run_tray, daemon=True).start()
        return tray
    except Exception as e:
        logger.warning("Tray icon unavailable: %s", e)
        return None


# ---------------------------------------------------------------------------
#                                Global hotkey
# ---------------------------------------------------------------------------


def _register_hotkey(api: Api):
    _HOTKEY_DEBOUNCE_DELAY = 0.3

    def _handler():
        try:
            import time
            import pyautogui
            time.sleep(_HOTKEY_DEBOUNCE_DELAY)
            pyautogui.hotkey('ctrl', 'l')
            time.sleep(0.3)
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(0.3)
            url = pyperclip.paste().strip()
            if url.startswith("http"):
                api.add_to_queue(url, 0, 1)
                logger.info("Hotkey triggered add_to_queue: %s", url)
        except Exception as e:
            logger.error("Hotkey handler error: %s", e)

    try:
        keyboard.add_hotkey("ctrl+shift+s", _handler)
    except Exception as e:
        logger.warning("Could not register global hotkey: %s", e)


# ---------------------------------------------------------------------------
#                                     Main
# ---------------------------------------------------------------------------


def main():
    setup_logging()
    set_app_user_model_id()

    lock = FileLock(_LOCK_FILE, timeout=0)
    try:
        lock.acquire()
    except Timeout:
        logger.info("Another instance is already running.")
        sys.exit(0)

    queue_manager = QueueManager()
    api = Api(queue_manager)

    ui_path = resource_path(os.path.join("ui", "index.html"))
    url = f"file:///{ui_path.replace(os.sep, '/')}"

    window = webview.create_window(
        title="Universal Video Downloader",
        url=url,
        js_api=api,
        width=900,
        height=600,
        min_size=(700, 500),
        frameless=True,
        easy_drag=False,
    )

    api.set_window(window)

    def _on_loaded():
        _register_hotkey(api)
        _build_tray(window)

    window.events.loaded += _on_loaded

    try:
        webview.start(debug=False)
    finally:
        lock.release()


if __name__ == "__main__":
    main()

