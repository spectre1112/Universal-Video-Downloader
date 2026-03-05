import json
import os
import uuid
import threading
import logging
from typing import List, Optional

from core.downloader import Downloader

logger = logging.getLogger(__name__)


class QueueManager:
    def __init__(self):
        self._items: List[dict] = []
        self._active_id: Optional[str] = None
        self._downloader = Downloader()
        self._lock = threading.RLock()
        self._load()

    @property
    def _save_path(self) -> str:
        return os.path.join(os.path.expanduser("~"), ".universal_video_downloader", "queue.json")

    def _save(self) -> None:
        """Persist completed/errored items to disk."""
        try:
            save_dir = os.path.dirname(self._save_path)
            os.makedirs(save_dir, exist_ok=True)
            to_save = [i for i in self._items if i["status"] in ("done", "error")]
            with open(self._save_path, "w", encoding="utf-8") as f:
                json.dump(to_save, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to save queue: %s", e)

    def _load(self) -> None:
        """Load persisted items on startup."""
        try:
            if os.path.exists(self._save_path):
                with open(self._save_path, "r", encoding="utf-8") as f:
                    items = json.load(f)
                self._items.extend(items)
        except Exception as e:
            logger.error("Failed to load queue: %s", e)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, url: str, type_idx: int, quality_idx: int, title: str = "", thumbnail: str = "") -> dict:
        item = {
            "id": str(uuid.uuid4()),
            "url": url,
            "title": title,
            "thumbnail": thumbnail,
            "status": "queued",
            "progress": 0,
            "speed": "",
            "type_idx": type_idx,
            "quality_idx": quality_idx,
            "file_path": None,
            "is_album": False,
        }
        with self._lock:
            self._items.append(item)
        logger.info("Queued: %s", url)
        self._maybe_start_next()
        return item

    def update_info(self, item_id: str, title: str, thumbnail: str) -> None:
        """Update title and thumbnail after async info fetch."""
        with self._lock:
            for item in self._items:
                if item["id"] == item_id:
                    if title:
                        item["title"] = title
                    if thumbnail:
                        item["thumbnail"] = thumbnail
                    break

    def get_all(self) -> List[dict]:
        with self._lock:
            return list(self._items)

    def clear_done(self) -> None:
        with self._lock:
            self._items = [i for i in self._items if i["status"] not in ("done", "error")]
            self._save()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _maybe_start_next(self) -> None:
        with self._lock:
            if self._active_id is not None:
                return
            for item in self._items:
                if item["status"] == "queued":
                    self._active_id = item["id"]
                    item["status"] = "analyzing"
                    self._start(item)
                    break

    def _start(self, item: dict) -> None:
        def on_progress(data: dict):
            with self._lock:
                item["progress"] = data.get("percent", 0)
                item["speed"] = data.get("speed", "")

        def on_status(status: str):
            with self._lock:
                if status == "done":
                    item["status"] = "done"
                elif status.startswith("error"):
                    item["status"] = "error"
                    logger.error("Item %s error: %s", item["id"], status)
                else:
                    # analyzing, downloading, merging, converting
                    item["status"] = status

        def on_finish(path: Optional[str]):
            with self._lock:
                if path:
                    item["file_path"] = path
                    item["status"] = "done"
                    item["progress"] = 100
                    # Mark as album if the returned path is a directory
                    if os.path.isdir(path):
                        item["is_album"] = True
                elif item["status"] != "done":
                    item["status"] = "error"
                self._active_id = None
                self._save()
            self._maybe_start_next()

        self._downloader.download(
            item["url"],
            item["type_idx"],
            item["quality_idx"],
            on_progress,
            on_status,
            on_finish,
        )
        logger.info("Started download: %s", item["url"])
