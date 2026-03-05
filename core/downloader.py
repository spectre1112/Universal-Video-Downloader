import os
import shutil
import threading
import logging
from typing import Callable, Optional
from urllib.parse import urlparse

import yt_dlp

from core.utils import resource_path

logger = logging.getLogger(__name__)

_RESOLUTIONS = ["2160p", "1080p", "720p"]
_RES_HEIGHTS  = [2160, 1080, 720]
_WINDOWS_FORBIDDEN_CHARS = r'\/:*?"<>|'
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}

# Try to import pytubefix; used only as an optional fallback for info fetching
try:
    from pytubefix import YouTube
    from pytubefix import request as pytubefix_request
    pytubefix_request.default_range_size = 4194304
    _PYTUBEFIX_AVAILABLE = True
except Exception:
    _PYTUBEFIX_AVAILABLE = False

# Try to import gallery-dl for TikTok photo albums
try:
    import gallery_dl
    _GALLERY_DL_AVAILABLE = True
except Exception:
    _GALLERY_DL_AVAILABLE = False


def _is_youtube(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
        return host.lower() in _YOUTUBE_HOSTS
    except Exception:
        return False


def _is_tiktok_photo(url: str) -> bool:
    """TikTok photo-album URLs contain /photo/ in the path."""
    try:
        parsed = urlparse(url)
        return "tiktok.com" in (parsed.hostname or "") and "/photo/" in parsed.path
    except Exception:
        return False


def _find_node_path() -> Optional[str]:
    """Find the Node.js binary. Prefers bundled portable node, falls back to system PATH."""
    bundled = resource_path(os.path.join("node", "node.exe"))
    if os.path.isfile(bundled):
        return bundled
    system = shutil.which("node")
    if system:
        return system
    logger.warning("Node.js not found. YouTube extraction may be limited.")
    return None


def _build_ydl_base_opts() -> dict:
    """Build common yt-dlp options including JS runtime and remote EJS components.

    Since yt-dlp >= 2025.11.12, YouTube requires an external JavaScript
    challenge solver (EJS) to decrypt the n-parameter.

    Notes:
    - ImpersonateTarget is intentionally NOT set: using curl_cffi Chrome
      impersonation causes ConnectionResetError (10054) on YouTube.
      yt-dlp's default HTTP client works fine.
    - ``remote_components`` must be a list, not a string — passing a plain
      string causes yt-dlp to iterate over its characters and emit
      "Ignoring unsupported remote component(s): g, h, j, s ..." warnings.

    See https://github.com/yt-dlp/yt-dlp/wiki/EJS for details.
    """
    opts: dict = {
        "quiet": True,
        "noplaylist": True,
        # ---- critical for YouTube since 2025.11.12 ----
        # Must be a list, not a bare string
        "remote_components": ["ejs:github"],
    }
    node_path = _find_node_path()
    if node_path:
        opts["js_runtimes"] = {"node": {"path": node_path}}
    else:
        opts["js_runtimes"] = {"node": {}}
    return opts


def _safe_title(title: str) -> str:
    return "".join(c for c in title if c not in _WINDOWS_FORBIDDEN_CHARS).strip() or "video"


# yt-dlp output template — uses %(field)s Python-style formatting
_OUTTMPL = "%(title)s.%(ext)s"


class Downloader:
    def __init__(self):
        self.downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_info(self, url: str) -> dict:
        """Return video metadata without downloading."""
        if _is_tiktok_photo(url):
            return {
                "title": "TikTok Photo Album",
                "thumbnail": "",
                "duration": "",
                "qualities": ["best"],
                "is_photo_album": True,
            }
        try:
            return self._info_ytdlp(url)
        except Exception as e:
            logger.error("get_info failed for %s: %s", url, e)
            return {"error": str(e)}

    def download(
        self,
        url: str,
        type_idx: int,
        quality_idx: int,
        on_progress: Callable[[dict], None],
        on_status: Callable[[str], None],
        on_finish: Callable[[Optional[str]], None],
    ) -> threading.Thread:
        """Start download in a background thread, return the thread."""
        t = threading.Thread(
            target=self._run,
            args=(url, type_idx, quality_idx, on_progress, on_status, on_finish),
            daemon=True,
        )
        t.start()
        return t

    # ------------------------------------------------------------------
    # Info helpers
    # ------------------------------------------------------------------

    def _info_ytdlp(self, url: str) -> dict:
        """Fetch metadata via yt-dlp (works for YouTube, TikTok, Instagram, etc.)"""
        ydl_opts = {
            **_build_ydl_base_opts(),
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        duration_sec = info.get("duration", 0) or 0
        m, s = divmod(int(duration_sec), 60)
        h, m = divmod(m, 60)
        duration_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

        # Best thumbnail: prefer the highest-res one
        thumbnail = info.get("thumbnail") or ""
        thumbs = info.get("thumbnails") or []
        if thumbs:
            best = max(
                thumbs,
                key=lambda t: (t.get("width") or 0) * (t.get("height") or 0),
                default=None,
            )
            if best:
                thumbnail = best.get("url", thumbnail)

        # For YouTube, expose available resolutions
        qualities = ["best"]
        if _is_youtube(url):
            found = []
            for fmt in info.get("formats", []):
                h_px = fmt.get("height") or 0
                for res, label in [(2160, "2160p"), (1080, "1080p"), (720, "720p")]:
                    if h_px >= res and label not in found:
                        found.append(label)
            qualities = found if found else ["best"]

        return {
            "title": info.get("title", ""),
            "thumbnail": thumbnail,
            "duration": duration_str,
            "qualities": qualities,
        }

    # ------------------------------------------------------------------
    # Download orchestration
    # ------------------------------------------------------------------

    def _run(self, url, type_idx, quality_idx, on_progress, on_status, on_finish):
        try:
            if _is_tiktok_photo(url):
                path = self._download_tiktok_photos(url, on_progress, on_status)
            elif _is_youtube(url):
                path = self._download_youtube_ytdlp(url, type_idx, quality_idx, on_progress, on_status)
            else:
                path = self._download_generic(url, quality_idx, on_progress, on_status)
            on_finish(path)
        except Exception as e:
            logger.error("Download failed for %s: %s", url, e)
            on_status(f"error: {e}")
            on_finish(None)

    # ------------------------------------------------------------------
    # Progress hook helper (shared by YouTube and generic downloaders)
    # ------------------------------------------------------------------

    @staticmethod
    def _make_progress_hook(final_path_holder, on_progress):
        """Return a yt-dlp progress hook closure."""

        def _hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                percent = int(downloaded / total * 100) if total > 0 else 0
                speed_raw = d.get("speed") or 0
                if speed_raw >= 1_048_576:
                    speed_str = f"{speed_raw / 1_048_576:.1f} MB/s"
                elif speed_raw >= 1024:
                    speed_str = f"{speed_raw / 1024:.1f} KB/s"
                else:
                    speed_str = f"{int(speed_raw)} B/s"
                on_progress({"percent": percent, "downloaded": downloaded, "total": total, "speed": speed_str})
            elif d["status"] == "finished":
                final_path_holder[0] = d.get("filename")

        return _hook

    # ------------------------------------------------------------------
    # YouTube via yt-dlp
    # ------------------------------------------------------------------

    def _download_youtube_ytdlp(self, url, type_idx, quality_idx, on_progress, on_status):
        on_status("analyzing")
        quality_idx = max(0, min(quality_idx, len(_RES_HEIGHTS) - 1))
        res = _RES_HEIGHTS[quality_idx]
        final_path_holder = [None]

        hook = self._make_progress_hook(final_path_holder, on_progress)

        if type_idx == 1:
            # Audio only -> MP3
            fmt = "bestaudio/best"
            postprocessors = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
        elif type_idx == 2:
            # Video only, no audio
            fmt = f"bestvideo[height<={res}]/bestvideo"
            postprocessors = []
        else:
            # Video + Audio merged
            fmt = f"bestvideo[height<={res}]+bestaudio/best"
            postprocessors = []

        outtmpl = os.path.join(self.downloads_dir, _OUTTMPL)

        ydl_opts = {
            **_build_ydl_base_opts(),
            "outtmpl": outtmpl,
            "format": fmt,
            "merge_output_format": "mp4",
            "ffmpeg_location": resource_path("ffmpeg.exe"),
            "progress_hooks": [hook],
            "postprocessors": postprocessors,
        }

        on_status("downloading")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if final_path_holder[0] is None:
                final_path_holder[0] = ydl.prepare_filename(info)
                # For MP3, yt-dlp changes the extension
                if type_idx == 1:
                    base, _ = os.path.splitext(final_path_holder[0])
                    mp3_path = base + ".mp3"
                    if os.path.exists(mp3_path):
                        final_path_holder[0] = mp3_path

        on_status("done")
        return final_path_holder[0]

    # ------------------------------------------------------------------
    # Generic (Instagram, TikTok video, etc.) via yt-dlp
    # ------------------------------------------------------------------

    def _download_generic(self, url, quality_idx, on_progress, on_status):
        on_status("analyzing")
        quality_idx = max(0, min(quality_idx, len(_RES_HEIGHTS) - 1))
        res = _RES_HEIGHTS[quality_idx]
        final_path_holder = [None]

        hook = self._make_progress_hook(final_path_holder, on_progress)

        ydl_opts = {
            **_build_ydl_base_opts(),
            "outtmpl": os.path.join(self.downloads_dir, _OUTTMPL),
            "progress_hooks": [hook],
            "ffmpeg_location": resource_path("ffmpeg.exe"),
            "format": f"bestvideo[height<={res}]+bestaudio/best",
            "merge_output_format": "mp4",
        }
        on_status("downloading")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if final_path_holder[0] is None:
                final_path_holder[0] = ydl.prepare_filename(info)

        on_status("done")
        return final_path_holder[0]

    # ------------------------------------------------------------------
    # TikTok photo albums via gallery-dl
    # ------------------------------------------------------------------

    def _download_tiktok_photos(self, url, on_progress, on_status):
        on_status("downloading")
        import uuid
        task_dir = os.path.join(self.downloads_dir, f"tiktok_photos_{uuid.uuid4().hex[:8]}")
        os.makedirs(task_dir, exist_ok=True)

        if _GALLERY_DL_AVAILABLE:
            from gallery_dl import config as gdl_config, job as gdl_job
            gdl_config.set(("extractor",), "base-directory", task_dir)
            gdl_config.set(("extractor",), "directory", [])
            j = gdl_job.DownloadJob(url)
            j.run()
        else:
            gallery_dl_path = resource_path("gallery-dl.exe")
            if not os.path.exists(gallery_dl_path):
                gallery_dl_path = shutil.which("gallery-dl") or "gallery-dl"

            import subprocess
            cmd = [gallery_dl_path, "--directory", task_dir, "--no-mtime", url]
            try:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=0x08000000,
                )
                if result.returncode != 0:
                    logger.warning("gallery-dl stderr: %s", result.stderr.decode(errors="replace"))
            except FileNotFoundError:
                raise RuntimeError("gallery-dl not found. Please install it or place gallery-dl.exe next to the app.")

        # Count downloaded files for progress
        files = []
        for root, _, filenames in os.walk(task_dir):
            for f in sorted(filenames):
                files.append(os.path.join(root, f))

        on_progress({"percent": 100, "downloaded": len(files), "total": len(files), "speed": ""})
        on_status("done")
        # Return the folder so the UI can open it in Explorer
        return task_dir