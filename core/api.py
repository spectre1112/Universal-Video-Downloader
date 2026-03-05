import base64
import logging
import mimetypes
import os
import threading
from typing import Optional

from core.queue_manager import QueueManager
from core.utils import open_explorer

logger = logging.getLogger(__name__)


class Api:
    """Bridge between pywebview JavaScript and Python backend."""

    def __init__(self, queue_manager: QueueManager):
        self._queue = queue_manager
        self._downloader = queue_manager._downloader
        self._window = None

    def set_window(self, window) -> None:
        self._window = window

    # ------------------------------------------------------------------
    # Queue
    # ------------------------------------------------------------------

    def add_to_queue(self, url: str, type_idx: int = 0, quality: str = "1080p") -> dict:
        try:
            item = self._queue.add(url, int(type_idx), str(quality), title="", thumbnail="")
            def _fetch_info():
                try:
                    info = self._downloader.get_info(url)
                    self._queue.update_info(item["id"], info.get("title", ""), info.get("thumbnail", ""))
                except Exception as e:
                    logger.warning("Background info fetch failed: %s", e)
            threading.Thread(target=_fetch_info, daemon=True).start()
            return {"ok": True, "id": item["id"]}
        except Exception as e:
            logger.error("add_to_queue error: %s", e)
            return {"ok": False, "error": str(e)}

    def get_queue(self) -> list:
        return self._queue.get_all()

    def clear_done(self) -> dict:
        self._queue.clear_done()
        return {"ok": True}

    # ------------------------------------------------------------------
    # Video info
    # ------------------------------------------------------------------

    def get_video_info(self, url: str) -> dict:
        try:
            return self._downloader.get_info(url)
        except Exception as e:
            logger.error("get_video_info error: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # File / window helpers
    # ------------------------------------------------------------------

    def open_file(self, path: str) -> dict:
        try:
            open_explorer(path)
            return {"ok": True}
        except Exception as e:
            logger.error("open_file error: %s", e)
            return {"ok": False, "error": str(e)}

    def minimize_to_tray(self) -> dict:
        try:
            if self._window:
                self._window.hide()
            return {"ok": True}
        except Exception as e:
            logger.error("minimize_to_tray error: %s", e)
            return {"ok": False, "error": str(e)}

    def close_window(self) -> dict:
        try:
            if self._window:
                self._window.destroy()
            return {"ok": True}
        except Exception as e:
            logger.error("close_window error: %s", e)
            return {"ok": False, "error": str(e)}

    def delete_item(self, item_id: str) -> dict:
        try:
            self._queue.delete_item(item_id)
            return {"ok": True}
        except Exception as e:
            logger.error("delete_item error: %s", e)
            return {"ok": False, "error": str(e)}

    def move_window(self, dx: int, dy: int) -> None:
        try:
            if self._window:
                x = self._window.x + int(dx)
                y = self._window.y + int(dy)
                self._window.move(x, y)
        except Exception as e:
            logger.error("move_window error: %s", e)

    def get_video_data_url(self, path: str) -> str:
        try:
            mime, _ = mimetypes.guess_type(path)
            if not mime:
                mime = "video/mp4"
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            return f"data:{mime};base64,{data}"
        except Exception as e:
            logger.error("get_video_data_url error: %s", e)
            return ""

    def get_album_files(self, folder_path: str) -> dict:
        images = []
        audio = None
        try:
            for f in sorted(os.listdir(folder_path)):
                path = os.path.join(folder_path, f)
                if not os.path.isfile(path):
                    continue
                mime, _ = mimetypes.guess_type(path)
                if not mime:
                    continue
                with open(path, "rb") as fh:
                    data = base64.b64encode(fh.read()).decode("ascii")
                data_url = f"data:{mime};base64,{data}"
                if mime.startswith("image/"):
                    images.append(data_url)
                elif mime.startswith("audio/") and audio is None:
                    audio = data_url
        except Exception as e:
            logger.error("get_album_files error: %s", e)
        return {"images": images, "audio": audio}

