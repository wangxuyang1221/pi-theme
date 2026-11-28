#!/usr/bin/env python3
"""2x Retina supersampled (3840x2160 lossless PNG pipe -> Lanczos 1080p60) single-pass demo renderer."""

from __future__ import annotations

import argparse
import base64
from concurrent.futures import ProcessPoolExecutor
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from PIL import Image
from playwright.sync_api import sync_playwright

DEFAULT_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def render_preview_sheet(
    html_uri: str,
    chrome_bin: str,
    out_dir: Path,
    width: int,
    height: int,
    stamps: list[float],
    crop_stamp: float | None,
) -> None:
    """Render key timestamps at 2x Retina into a contact sheet plus an optional 1:1 sharpness crop."""
    thumbs: list[Image.Image] = []
    sharp_crop: Image.Image | None = None
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_bin, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=2)
        page.goto(html_uri, wait_until="load")
        page.evaluate("() => document.fonts.ready")
        for s in stamps:
            page.evaluate("(t) => window.renderAt(t)", s)
            raw = page.screenshot(type="png")
            im_full = Image.open(BytesIO(raw)).resize((width, height), Image.Resampling.LANCZOS)
            if crop_stamp is not None and abs(s - crop_stamp) < 1e-6:
                sharp_crop = im_full.crop((int(width * 0.36), int(height * 0.16), int(width * 0.93), int(height * 0.84)))
            thumbs.append(im_full.resize((640, 360), Image.Resampling.LANCZOS))
        browser.close()

    cols = 3
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (640 * cols, 360 * rows), (10, 10, 14))
    for i, im in enumerate(thumbs):
        r, c = divmod(i, cols)
        sheet.paste(im, (c * 640, r * 360))
    sheet_path = out_dir / "preview_sheet.png"
    sheet.save(sheet_path)
    if sharp_crop is not None:
        crop_path = out_dir / "sharpness_1to1.png"
        sharp_crop.save(crop_path)
        print(f"Saved preview sheet: {sheet_path} and 1:1 crop: {crop_path}")
    else:
        print(f"Saved preview sheet: {sheet_path}")


def _render_chunk(args: tuple[int, int, int, str, str, str, int, int, int, int]) -> str:
    chunk_id, start_f, end_f, out_path, html_uri, chrome_bin, width, height, fps, crf = args
    # Lossless 2x Retina PNG pipe -> Lanczos downscale -> single-pass H.264 (concat uses -c:v copy)
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-loglevel", "error",
        "-f", "image2pipe",
        "-vcodec", "png",
        "-framerate", str(fps),
        "-i", "-",
        "-vf", f"scale={width}:{height}:flags=lanczos",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", str(crf),
        "-g", str(fps),
        "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-colorspace", "bt709",
        out_path,
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_bin, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=2)
        page.goto(html_uri, wait_until="load")
        page.evaluate("() => document.fonts.ready")
        cdp = page.context.new_cdp_session(page)

        for f in range(start_f, end_f):
            t = f / fps
            page.evaluate("(t) => window.renderAt(t)", t)
            res = cdp.send("Page.captureScreenshot", {"format": "png"})
            proc.stdin.write(base64.b64decode(res["data"]))

        browser.close()

    proc.stdin.close()
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(f"ffmpeg chunk {chunk_id} exited with {ret}")
    return out_path


def render_full(
    html_uri: str,
    chrome_bin: str,
    audio_path: Path | None,
    out_mp4: Path,
    width: int,
    height: int,
    fps: int,
    duration: float,
    workers: int,
    crf: int,
) -> None:
    t0 = time.time()
    total_frames = int(round(duration * fps))
    chunks_dir = Path(tempfile.mkdtemp(prefix=f".chunks-{out_mp4.stem}-", dir=out_mp4.parent))

    try:
        # Align chunk boundaries to whole seconds so GOP keyframes line up for lossless -c:v copy concat
        total_secs = max(1, (total_frames + fps - 1) // fps)
        secs_per = max(1, (total_secs + workers - 1) // workers)
        jobs = []
        for i in range(workers):
            sf = i * secs_per * fps
            ef = min(total_frames, (i + 1) * secs_per * fps)
            if sf >= ef:
                break
            jobs.append((i, sf, ef, str(chunks_dir / f"part_{i:02d}.mp4"), html_uri, chrome_bin, width, height, fps, crf))

        print(f"Rendering {total_frames} frames at 2x Retina ({width*2}x{height*2} -> Lanczos {width}x{height}@{fps}fps) across {len(jobs)} workers...")
        with ProcessPoolExecutor(max_workers=len(jobs)) as ex:
            parts = list(ex.map(_render_chunk, jobs))

        concat_txt = chunks_dir / "concat.txt"
        concat_txt.write_text("\n".join(f"file '{Path(p).resolve()}'" for p in parts) + "\n")

        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_txt)]
        if audio_path is not None:
            cmd += ["-i", str(audio_path), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest"]
        else:
            cmd += ["-c:v", "copy"]
        cmd += ["-movflags", "+faststart", str(out_mp4)]
        subprocess.run(cmd, check=True)
        elapsed = time.time() - t0
        size_mb = out_mp4.stat().st_size / 1024 / 1024
        print(f"Done in {elapsed:.1f}s -> {out_mp4} ({size_mb:.2f} MB)")
    finally:
        shutil.rmtree(chunks_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render deterministic HTML/JS UI motion demos at 2x Retina 1080p60.")
    parser.add_argument("--html", required=True, help="Path to demo HTML file exposing window.renderAt(t).")
    parser.add_argument("--audio", help="Optional WAV/AAC audio file to mux with video.")
    parser.add_argument("--out", help="Output MP4 path (or preview output directory when --preview is set).")
    parser.add_argument("--duration", type=float, default=38.0, help="Duration in seconds (default: 38.0).")
    parser.add_argument("--fps", type=int, default=60, help="Frame rate (default: 60).")
    parser.add_argument("--width", type=int, default=1920, help="Output width (default: 1920).")
    parser.add_argument("--height", type=int, default=1080, help="Output height (default: 1080).")
    parser.add_argument("--workers", type=int, default=6, help="Parallel Chromium workers (default: 6).")
    parser.add_argument("--crf", type=int, default=13, help="H.264 CRF quality (default: 13).")
    parser.add_argument("--chrome", default=DEFAULT_CHROME, help="Chrome/Chromium executable path.")
    parser.add_argument("--preview", action="store_true", help="Render contact sheet + 1:1 crop instead of full MP4.")
    parser.add_argument("--stamps", help="Comma-separated preview timestamps in seconds.")
    parser.add_argument("--crop-stamp", type=float, help="Timestamp in --stamps to also save as 1:1 sharpness_1to1.png.")
    args = parser.parse_args()

    html_path = Path(args.html).resolve()
    if not html_path.is_file():
        raise FileNotFoundError(f"HTML file not found: {html_path}")
    html_uri = html_path.as_uri()

    if args.preview:
        if args.stamps:
            stamps = [float(s.strip()) for s in args.stamps.split(",") if s.strip()]
        else:
            stamps = [round(args.duration * (i + 0.5) / 12.0, 2) for i in range(12)]
        crop_s = args.crop_stamp if args.crop_stamp is not None else stamps[len(stamps) // 2]
        out_dir = Path(args.out).resolve() if args.out else html_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        render_preview_sheet(html_uri, args.chrome, out_dir, args.width, args.height, stamps, crop_s)
        return

    out_mp4 = Path(args.out).resolve() if args.out else html_path.with_suffix(".mp4")
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    audio_path = Path(args.audio).resolve() if args.audio else None
    if audio_path is not None and not audio_path.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    render_full(html_uri, args.chrome, audio_path, out_mp4, args.width, args.height, args.fps, args.duration, args.workers, args.crf)


if __name__ == "__main__":
    main()
