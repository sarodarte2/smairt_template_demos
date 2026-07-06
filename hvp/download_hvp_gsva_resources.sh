#!/usr/bin/env bash
# Download GSVA resources for the HVP demo from Figshare.
# Run from demos/hvp before building the database:
#   bash download_hvp_gsva_resources.sh

set -Eeuo pipefail

FIGSHARE_ARTICLE_ID="${FIGSHARE_ARTICLE_ID:-32600796}"
GSVA_DIR="${GSVA_DIR:-build/resource/GSVA}"
DOWNLOAD_DIR="${DOWNLOAD_DIR:-${GSVA_DIR}/_figshare_downloads}"

mkdir -p "${GSVA_DIR}" "${DOWNLOAD_DIR}"

python3 - <<'PY'
from __future__ import annotations

import json
import os
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ARTICLE_ID = os.environ.get("FIGSHARE_ARTICLE_ID", "32600796")
GSVA_DIR = Path(os.environ.get("GSVA_DIR", "build/resource/GSVA"))
DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", str(GSVA_DIR / "_figshare_downloads")))

EXPECTED = {
    "AMG_withCAT_new.txt",
    "GSVA_all_soil_viruses_1.fna",
    "GSVA_sample_metadata_5.csv",
    "GSVA_soil_viruses_3.faa",
    "GSVA_soil_viruses_gene_metadata_4.tsv",
    "GSVA_soil_viruses_genome_metadata_2.tsv",
    "README_Global_Soil_Virus_Atlas.txt",
}

API_URL = f"https://api.figshare.com/v2/articles/{ARTICLE_ID}"
USER_AGENT = "SMAIRT-HVP-demo-downloader/1.0"


def request_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=60) as response:
            return json.load(response)
    except HTTPError as exc:
        body = exc.read(500).decode("utf-8", "replace")
        raise SystemExit(
            f"ERROR: Figshare article {ARTICLE_ID} is not available through the public API yet.\n"
            f"URL: {url}\n"
            f"HTTP {exc.code}: {exc.reason}\n"
            f"Response preview: {body}\n\n"
            "Publish the Figshare article, or set FIGSHARE_ARTICLE_ID to the published article ID, then rerun."
        ) from exc
    except URLError as exc:
        raise SystemExit(f"ERROR: Could not reach Figshare API: {exc.reason}") from exc


def download_file(url: str, destination: Path) -> None:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=120) as response, destination.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            downloaded += len(chunk)
            if total:
                print(f"  {destination.name}: {downloaded / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MiB", end="\r")
        if total:
            print()


def safe_target_for(member_name: str) -> Path | None:
    basename = Path(member_name).name
    if not basename or basename.startswith("."):
        return None
    return GSVA_DIR / basename


def extract_zip(archive: Path) -> None:
    print(f"Extracting {archive.name} into {GSVA_DIR}...")
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            target = safe_target_for(info.filename)
            if target is None:
                continue
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            print(f"  wrote {target}")


def extract_tar(archive: Path) -> None:
    print(f"Extracting {archive.name} into {GSVA_DIR}...")
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            target = safe_target_for(member.name)
            if target is None:
                continue
            src = tf.extractfile(member)
            if src is None:
                continue
            with src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            print(f"  wrote {target}")


def handle_downloaded_file(path: Path) -> None:
    lower = path.name.lower()
    if lower.endswith(".zip"):
        extract_zip(path)
    elif lower.endswith((".tar", ".tar.gz", ".tgz")):
        extract_tar(path)
    else:
        target = GSVA_DIR / path.name
        if path.resolve() != target.resolve():
            shutil.copy2(path, target)
        print(f"  wrote {target}")


def main() -> None:
    GSVA_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    article = request_json(API_URL)
    files = article.get("files", [])
    if not files:
        raise SystemExit(f"ERROR: Figshare article {ARTICLE_ID} has no files.")

    print(f"Figshare article: {article.get('title', ARTICLE_ID)}")
    print(f"Files listed: {len(files)}")

    for file_info in files:
        name = file_info.get("name")
        url = file_info.get("download_url")
        size = int(file_info.get("size") or 0)
        if not name or not url:
            raise SystemExit(f"ERROR: Figshare file entry is missing name or download_url: {file_info}")

        destination = DOWNLOAD_DIR / name
        if destination.exists() and size and destination.stat().st_size == size:
            print(f"Already downloaded: {destination}")
        else:
            print(f"Downloading {name} ({size / 1024 / 1024:.1f} MiB)...")
            download_file(url, destination)
        handle_downloaded_file(destination)

    missing = sorted(name for name in EXPECTED if not (GSVA_DIR / name).exists())
    if missing:
        print("\nERROR: Expected GSVA files are still missing:", file=sys.stderr)
        for name in missing:
            print(f"  {GSVA_DIR / name}", file=sys.stderr)
        print(
            "\nCheck that the Figshare article contains either these files directly "
            "or an archive containing them.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print("\nGSVA resource download complete. Required files are present:")
    for name in sorted(EXPECTED):
        path = GSVA_DIR / name
        print(f"  {path} ({path.stat().st_size / 1024 / 1024:.1f} MiB)")


if __name__ == "__main__":
    main()
PY
