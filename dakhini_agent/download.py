"""Local audio downloads: 30 s sample and full file."""
import subprocess
from pathlib import Path

import requests
import yt_dlp

from . import config
from .models import Candidate


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)[:80]


def download_sample(c: Candidate, workdir: Path) -> Path | None:
    workdir.mkdir(parents=True, exist_ok=True)
    out = workdir / f"{_safe(c.key())}_sample.mp3"
    start = config.SAMPLE_OFFSET_SECONDS
    if c.duration and c.duration < start + config.SAMPLE_SECONDS:
        start = 0
    try:
        if c.source == "youtube":
            tmp = workdir / f"{_safe(c.key())}_raw.%(ext)s"
            opts = {
                "quiet": True, "no_warnings": True, "format": "bestaudio/best",
                "outtmpl": str(tmp),
                "download_ranges": yt_dlp.utils.download_range_func(
                    None, [(start, start + config.SAMPLE_SECONDS)]),
                "force_keyframes_at_cuts": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(c.url, download=True)
                raw = Path(ydl.prepare_filename(info))
            _to_mp3(raw, out)
            raw.unlink(missing_ok=True)
        else:
            _ffmpeg(["-ss", str(start), "-t", str(config.SAMPLE_SECONDS), "-i", c.url], out)
    except Exception as e:  # noqa: BLE001
        print(f"  [sample failed] {c.key()}: {e}")
        return None
    return out if out.exists() and out.stat().st_size > 1000 else None


def download_full(c: Candidate, workdir: Path) -> Path | None:
    workdir.mkdir(parents=True, exist_ok=True)
    out = workdir / f"{_safe(c.key())}.mp3"
    try:
        if c.source == "youtube":
            opts = {
                "quiet": True, "no_warnings": True, "format": "bestaudio/best",
                "outtmpl": str(workdir / f"{_safe(c.key())}.%(ext)s"),
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                                    "preferredquality": "64"}],
                "max_filesize": config.MAX_FULL_DOWNLOAD_MB * 1024 * 1024,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([c.url])
        else:
            with requests.get(c.url, stream=True, timeout=60) as r:
                r.raise_for_status()
                raw = workdir / f"{_safe(c.key())}.raw"
                size = 0
                with open(raw, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        size += len(chunk)
                        if size > config.MAX_FULL_DOWNLOAD_MB * 1024 * 1024:
                            raise RuntimeError("file too large")
                        f.write(chunk)
            _to_mp3(raw, out)
            raw.unlink(missing_ok=True)
    except Exception as e:  # noqa: BLE001
        print(f"  [full download failed] {c.key()}: {e}")
        return None
    return out if out.exists() else None


def _to_mp3(src: Path, dst: Path):
    _ffmpeg(["-i", str(src)], dst)


def _ffmpeg(input_args: list[str], dst: Path):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *input_args,
           "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(dst)]
    subprocess.run(cmd, check=True, timeout=600)
