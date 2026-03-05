import os
import shutil
import threading
import logging
from typing import Callable, Optional
from urllib.parse import urlparse

import yt_dlp

from core.utils import resource_path

logger = logging.getLogger(__name__)

_RESOLUTIONS = ["2160p", "1440p", "1080p", "720p", "360p"]
_RES_HEIGHTS  = [2160,   1440,   1080,   720,   360]
_WINDOWS_FORBIDDEN_CHARS = r'\/:*?"<>|'
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}
_TIKTOK_HOSTS  = {"tiktok.com", "www.tiktok.com", "vm.tiktok.com", "m.tiktok.com"}

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


def _is_tiktok(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
        return host.lower() in _TIKTOK_HOSTS
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
    """yt-dlp options for YouTube (no impersonate — causes curl 35 on YT)."""
    opts: dict = {
        "quiet": True,
        "noplaylist": True,
        "remote_components": ["ejs:github"],
    }
    node_path = _find_node_path()
    if node_path:
        opts["js_runtimes"] = {"node": {"path": node_path}}
    else:
        opts["js_runtimes"] = {"node": {}}
    return opts


def _build_ydl_generic_opts() -> dict:
    """yt-dlp options for TikTok / Instagram / other (uses Chrome impersonation).

    Impersonate is required for TikTok — without it yt-dlp gets blocked and
    cannot fetch metadata or video streams.  It must NOT be used for YouTube
    because curl_cffi causes ConnectionResetError (10054) there.
    """
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget
        impersonate = ImpersonateTarget(client="chrome")
    except Exception:
        impersonate = None

    opts: dict = {
        "quiet": True,
        "noplaylist": True,
    }
    if impersonate is not None:
        opts["impersonate"] = impersonate
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
                "platform": "tiktok",
                "qualities": None,  # None = hide quality selector
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
        quality: str,
        on_progress: Callable[[dict], None],
        on_status: Callable[[str], None],
        on_finish: Callable[[Optional[str]], None],
    ) -> threading.Thread:
        """Start download in a background thread, return the thread."""
        t = threading.Thread(
            target=self._run,
            args=(url, type_idx, quality, on_progress, on_status, on_finish),
            daemon=True,
        )
        t.start()
        return t

    # ------------------------------------------------------------------
    # Info helpers
    # ------------------------------------------------------------------

    def _info_ytdlp(self, url: str) -> dict:
        """Fetch metadata via yt-dlp."""
        is_yt = _is_youtube(url)
        ydl_opts = {
            **(  _build_ydl_base_opts() if is_yt else _build_ydl_generic_opts()),
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        duration_sec = info.get("duration", 0) or 0
        m, s = divmod(int(duration_sec), 60)
        h, m = divmod(m, 60)
        duration_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

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

        # YouTube: expose available resolutions from actual formats
        # TikTok / Instagram / other: qualities=None → hide selector, always use best
        if is_yt:
            found = []
            for fmt in info.get("formats", []):
                h_px = fmt.get("height") or 0
                for res, label in [(2160, "2160p"), (1440, "1440p"), (1080, "1080p"), (720, "720p"), (360, "360p")]:
                    if h_px >= res and label not in found:
                        found.append(label)
            # Sort highest first
            order = ["2160p", "1440p", "1080p", "720p", "360p"]
            qualities = [q for q in order if q in found] or ["1080p"]
            platform = "youtube"
        else:
            qualities = None  # hide quality selector
            platform = "tiktok" if _is_tiktok(url) else "generic"

        return {
            "title": info.get("title", ""),
            "thumbnail": thumbnail,
            "duration": duration_str,
            "qualities": qualities,
            "platform": platform,
        }

    # ------------------------------------------------------------------
    # Download orchestration
    # ------------------------------------------------------------------

    def _run(self, url, type_idx, quality, on_progress, on_status, on_finish):
        try:
            if _is_tiktok_photo(url):
                path = self._download_tiktok_photos(url, on_progress, on_status)
            elif _is_youtube(url):
                path = self._download_youtube_ytdlp(url, type_idx, quality, on_progress, on_status)
            else:
                path = self._download_generic(url, quality, on_progress, on_status)
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
        """Return a yt-dlp progress hook closure.

        yt-dlp fires ``finished`` once per stream when downloading separate
        audio/video tracks, then merges them into a single .mp4.  We must
        NOT store the intermediate filenames (e.g. .m4a, .webm) because they
        are deleted after the merge.  Instead we leave final_path_holder[0]
        as None and resolve the real path after extract_info() returns.
        """

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
            # Intentionally skip "finished" — intermediate streams (.m4a/.webm)
            # are deleted after merging; the real path is resolved post-download.

        return _hook

    # ------------------------------------------------------------------
    # YouTube via yt-dlp
    # ------------------------------------------------------------------

    def _download_youtube_ytdlp(self, url, type_idx, quality, on_progress, on_status):
        on_status("analyzing")
        # quality is a string like "1080p", "720p", etc.
        # Map to pixel height; default to 1080 if unknown
        height_map = {"2160p": 2160, "1440p": 1440, "1080p": 1080, "720p": 720, "360p": 360}
        res = height_map.get(str(quality), 1080)

        hook = self._make_progress_hook(None, on_progress)

        if type_idx == 1:
            fmt = "bestaudio/best"
            postprocessors = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
        elif type_idx == 2:
            fmt = f"bestvideo[height<={res}]/bestvideo"
            postprocessors = []
        else:
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
            raw = ydl.prepare_filename(info)
            base, _ = os.path.splitext(raw)
            if type_idx == 1:
                final_path = base + ".mp3"
            else:
                mp4_path = base + ".mp4"
                final_path = mp4_path if os.path.exists(mp4_path) else raw

        on_status("done")
        return final_path

    # ------------------------------------------------------------------
    # Generic (Instagram, TikTok video, etc.) via yt-dlp
    # ------------------------------------------------------------------

    def _download_generic(self, url, quality_idx, on_progress, on_status):
        on_status("analyzing")
        hook = self._make_progress_hook(None, on_progress)

        ydl_opts = {
            **_build_ydl_generic_opts(),
            "outtmpl": os.path.join(self.downloads_dir, _OUTTMPL),
            "progress_hooks": [hook],
            "ffmpeg_location": resource_path("ffmpeg.exe"),
            # Always best quality for TikTok/Instagram — no user choice
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
        }
        on_status("downloading")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            raw = ydl.prepare_filename(info)
            base, _ = os.path.splitext(raw)
            mp4_path = base + ".mp4"
            final_path = mp4_path if os.path.exists(mp4_path) else raw

        on_status("done")
        return final_path

    # ------------------------------------------------------------------
    # TikTok photo albums via gallery-dl
    # ------------------------------------------------------------------

    def _download_tiktok_photos(self, url, on_progress, on_status):
        on_status("downloading")
        import uuid
        task_dir = os.path.join(self.downloads_dir, f"tiktok_photos_{uuid.uuid4().hex[:8]}")
        os.makedirs(task_dir, exist_ok=True)

        if _GALLERY_DL_AVAILABLE:
            from gallery_dl import config as gdl_config, job as gdl_job, output as gdl_output

            gdl_config.set(("extractor",), "base-directory", task_dir)
            gdl_config.set(("extractor",), "directory", [])

            # Patch gallery-dl's status line to extract real-time progress
            _downloaded = [0]
            _original_status = getattr(gdl_output, "stderr", None)

            class _ProgressJob(gdl_job.DownloadJob):
                def handle_url(self, url, kwdict):
                    result = super().handle_url(url, kwdict)
                    _downloaded[0] += 1
                    # We don't know total upfront, report indeterminate progress
                    on_progress({"percent": 0, "downloaded": _downloaded[0], "total": 0, "speed": ""})
                    return result

            j = _ProgressJob(url)
            j.run()
            total = _downloaded[0]
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
            total = sum(len(files) for _, _, files in os.walk(task_dir))

        on_progress({"percent": 100, "downloaded": total, "total": total, "speed": ""})
        on_status("done")
        # Return the folder so the UI can open it in Explorer
        return task_dir
