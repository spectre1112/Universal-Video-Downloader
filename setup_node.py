"""
setup_node.py — Download portable Node.js for Windows x64.

Run this script once before first use:
    python setup_node.py

It downloads node.exe from the official Node.js distribution and places it at
node/node.exe, where core/downloader.py will automatically detect it.
"""

import os
import zipfile
import urllib.request

NODE_VERSION = "v22.16.0"
NODE_ZIP_URL = f"https://nodejs.org/dist/{NODE_VERSION}/node-{NODE_VERSION}-win-x64.zip"
NODE_ZIP_NAME = f"node-{NODE_VERSION}-win-x64.zip"
NODE_EXE_IN_ZIP = f"node-{NODE_VERSION}-win-x64/node.exe"
DEST_DIR = "node"
DEST_EXE = os.path.join(DEST_DIR, "node.exe")


def main():
    if os.path.isfile(DEST_EXE):
        print(f"node.exe already exists at {DEST_EXE}. Nothing to do.")
        return

    os.makedirs(DEST_DIR, exist_ok=True)

    print(f"Downloading {NODE_ZIP_URL} ...")
    urllib.request.urlretrieve(NODE_ZIP_URL, NODE_ZIP_NAME)
    print("Download complete.")

    print(f"Extracting {NODE_EXE_IN_ZIP} ...")
    with zipfile.ZipFile(NODE_ZIP_NAME, "r") as zf:
        with zf.open(NODE_EXE_IN_ZIP) as src, open(DEST_EXE, "wb") as dst:
            dst.write(src.read())
    print(f"Extracted node.exe to {DEST_EXE}")

    os.remove(NODE_ZIP_NAME)
    print("Cleaned up zip file.")
    print(f"\nSuccess! node.exe is ready at {DEST_EXE}")


if __name__ == "__main__":
    main()
