import sys
import os
import subprocess
import logging
import ctypes

logger = logging.getLogger(__name__)


def setup_logging():
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler("downloader.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def resource_path(relative_path: str) -> str:
    """Return absolute path to resource, works for dev and for PyInstaller."""
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def open_explorer(path: str) -> None:
    """Open a file or folder in Windows Explorer."""
    path = os.path.normpath(path)
    try:
        if os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", path])
        else:
            subprocess.Popen(["explorer", path])
    except Exception as e:
        logger.error("Failed to open explorer for %s: %s", path, e)


def set_app_user_model_id(app_id: str = "video.downloader.v2.0.0") -> None:
    """Set AppUserModelID for correct taskbar icon on Windows."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception as e:
        logger.warning("Could not set AppUserModelID: %s", e)
