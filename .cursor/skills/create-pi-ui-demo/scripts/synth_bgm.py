#!/usr/bin/env python3
"""Procedural BGM + synchronized UI SFX synthesizer for Pi UI product demos (48kHz stereo WAV)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

SR = 48000


def midi_to_hz(m: float) -> float:
    return 440.0 * (2.0 ** ((m - 69.0) / 12.0))


def add_stereo(buf: np.ndarray, start_s: float, sig: np.ndarray, pan: float = 0.0, gain: float = 1.0) -> None:
    total = len(buf)
    idx = int(round(start_s * SR))
    if idx >= total or idx + len(sig) <= 0:
        return
    src_start = max(0, -idx)
    dst_start = max(0, idx)
    length = min(len(sig) - src_start, total - dst_start)
    if length <= 0:
        return
    chunk = sig[src_start : src_start + length] * gain
    if chunk.ndim == 2:
        buf[dst_start : dst_start + length] += chunk
    else:
        angle = (pan + 1.0) * 0.25 * np.pi
        buf[dst_start : dst_start + length, 0] += chunk * np.cos(angle)
        buf[dst_start : dst_start + length, 1] += chunk * np.sin(angle)


def synth_epiano_note(freq: float, dur: float, vel: float = 0.7) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    env = np.exp(-t * 2.1) * (1.0 - np.exp(-t * 240.0))
    tine_env = np.exp(-t * 18.0) * (1.0 - np.exp(-t * 450.0))
    vib = 1.0 + 0.0018 * np.sin(2 * np.pi * 4.2 * t)
    ph = 2 * np.pi * freq * np.cumsum(vib) / SR
    sig = (
        0.72 * np.sin(ph) * env
        + 0.18 * np.sin(2 * ph) * np.exp(-t * 3.8) * (1.0 - np.exp(-t * 240.0))
        + 0.08 * np.sin(3 * ph) * tine_env
        + 0.05 * np.sin(7 * ph) * np.exp(-t * 34.0)
    )
    fade = np.linspace(1.0, 0.0, min(len(sig), int(0.05 * SR)))
    sig[-len(fade) :] *= fade
    return sig * vel


def synth_pluck(freq: float, dur: float, vel: float = 0.5) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    env = np.exp(-t * 6.5) * (1.0 - np.exp(-t * 500.0))
    return (
        0.78 * np.sin(2 * np.pi * freq * t)
        + 0.22 * np.sin(2 * np.pi * freq * 2.0 * t) * np.exp(-t * 14.0)
        + 0.10 * np.sin(2 * np.pi * freq * 3.98 * t) * np.exp(-t * 28.0)
    ) * env * vel


def synth_pad_chord(freqs: list[float], dur: float, vel: float = 0.16) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    env = np.minimum(1.0, t / 0.45) * np.minimum(1.0, np.maximum(0.0, dur - t) / 0.65)
    left = np.zeros_like(t)
    right = np.zeros_like(t)
    for i, f in enumerate(freqs):
        d = 0.0025 * (i % 2 * 2 - 1)
        left += np.sin(2 * np.pi * f * (1 + d) * t) + 0.25 * np.sin(2 * np.pi * f * 2 * (1 - d) * t)
        right += np.sin(2 * np.pi * f * (1 - d) * t) + 0.25 * np.sin(2 * np.pi * f * 2 * (1 + d) * t)
    sos = butter(3, 1400 / (SR / 2), btype="low", output="sos")
    return np.stack([sosfilt(sos, left), sosfilt(sos, right)], axis=1) * (env[:, None] * vel / len(freqs))


def synth_bass(freq: float, dur: float, vel: float = 0.30) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    env = np.exp(-t * 2.0) * (1.0 - np.exp(-t * 120.0))
    sig = (0.8 * np.sin(2 * np.pi * freq * t) + 0.2 * np.sin(2 * np.pi * freq * 2 * t)) * env
    fade = np.linspace(1.0, 0.0, min(len(sig), int(0.03 * SR)))
    sig[-len(fade) :] *= fade
    return sig * vel


def synth_soft_kick() -> np.ndarray:
    t = np.arange(int(0.18 * SR)) / SR
    ph = 2 * np.pi * np.cumsum(48.0 + 95.0 * np.exp(-t * 36.0)) / SR
    return np.sin(ph) * np.exp(-t * 17.0) * (1.0 - np.exp(-t * 700.0)) * 0.48


def synth_soft_hat(rng: np.random.Generator, open_hat: bool = False) -> np.ndarray:
    dur = 0.11 if open_hat else 0.042
    t = np.arange(int(dur * SR)) / SR
    sos = butter(3, [6500 / (SR / 2), 14500 / (SR / 2)], btype="bandpass", output="sos")
    filt = sosfilt(sos, rng.standard_normal(len(t)))
    env = np.exp(-t * (22.0 if open_hat else 78.0)) * (1.0 - np.exp(-t * 1500.0))
    return filt * env * (0.14 if open_hat else 0.09)


def synth_rim_click(rng: np.random.Generator) -> np.ndarray:
    t = np.arange(int(0.055 * SR)) / SR
    tone = np.sin(2 * np.pi * 840.0 * t) * np.exp(-t * 68.0)
    snap = sosfilt(butter(2, 2600 / (SR / 2), btype="high", output="sos"), rng.standard_normal(len(t))) * np.exp(-t * 110.0)
    return (tone * 0.4 + snap * 0.22) * 0.24


def sfx_key_tap(rng: np.random.Generator, pitch_mul: float = 1.0) -> np.ndarray:
    t = np.arange(int(0.032 * SR)) / SR
    body = np.sin(2 * np.pi * (420.0 * pitch_mul) * t) * np.exp(-t * 140.0)
    click = sosfilt(butter(2, [1800 / (SR / 2), 6200 / (SR / 2)], btype="bandpass", output="sos"), rng.standard_normal(len(t))) * np.exp(-t * 210.0)
    return (body * 0.45 + click * 0.9) * 0.26


def sfx_whoosh(rng: np.random.Generator, dur: float = 0.42, up: bool = True) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    noise = rng.standard_normal(len(t))
    env = np.sin(np.pi * (t / dur)) ** 1.6
    lo = sosfilt(butter(2, [280 / (SR / 2), 1400 / (SR / 2)], btype="bandpass", output="sos"), noise)
    hi = sosfilt(butter(2, [900 / (SR / 2), 3400 / (SR / 2)], btype="bandpass", output="sos"), noise)
    blend = (t / dur) if up else (1.0 - t / dur)
    return (lo * (1.0 - 0.55 * blend) + hi * (0.55 * blend)) * env * 0.22


def sfx_ui_pop(f0: float = 520.0, f1: float = 880.0, dur: float = 0.11) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    ph = 2 * np.pi * np.cumsum(f0 + (f1 - f0) * (1.0 - np.exp(-t * 32.0))) / SR
    return np.sin(ph) * np.exp(-t * 28.0) * (1.0 - np.exp(-t * 600.0)) * 0.28


def sfx_chime(notes: list[float], step: float = 0.065, gain: float = 0.26) -> np.ndarray:
    out = np.zeros(int((step * len(notes) + 0.9) * SR))
    for i, m in enumerate(notes):
        s = synth_epiano_note(midi_to_hz(m), 0.85, vel=0.75)
        st = int(i * step * SR)
        end = min(len(out), st + len(s))
        out[st:end] += s[: end - st]
    return out * gain


def add_stereo_reverb(stereo: np.ndarray) -> np.ndarray:
    out = stereo.copy()
    for delay_s, gl, gr in [(0.031, 0.19, 0.12), (0.053, 0.11, 0.17), (0.089, 0.13, 0.09), (0.137, 0.08, 0.11), (0.211, 0.06, 0.05)]:
        d = int(delay_s * SR)
        if d < len(stereo):
            out[d:, 0] += stereo[:-d, 0] * gl + stereo[:-d, 1] * (gr * 0.45)
            out[d:, 1] += stereo[:-d, 1] * gr + stereo[:-d, 0] * (gl * 0.45)
    return out


def render_audio(duration: float, bpm: float, outro_at: float | None, events: list[dict], seed: int) -> np.ndarray:
    n = int(round(SR * duration))
    rng = np.random.default_rng(seed)
    bgm = np.zeros((n, 2), dtype=np.float64)
    sfx = np.zeros((n, 2), dtype=np.float64)

    beat = 60.0 / bpm
    bar_sec = 4.0 * beat
    resolve_t = outro_at if outro_at is not None else max(0.0, duration - 3.9)
    chords = [
        ([53, 60, 64, 69, 72], 41),  # Fmaj7
        ([55, 62, 64, 67, 71], 43),  # G6
        ([52, 59, 62, 67, 71], 40),  # Em7
        ([57, 60, 64, 67, 71], 45),  # Am9
    ]
    melody = [
        [(0.0, 76), (1.0, 79), (1.5, 76), (2.5, 72), (3.5, 74)],
        [(0.0, 74), (1.0, 76), (2.0, 79), (3.0, 81), (3.5, 79)],
        [(0.0, 76), (1.0, 74), (1.5, 71), (2.5, 72), (3.5, 74)],
        [(0.0, 76), (1.5, 79), (2.5, 84), (3.5, 81)],
    ]

    kick = synth_soft_kick()
    bar = 0
    while bar * bar_sec < resolve_t - 0.15:
        bar_t = bar * bar_sec
        notes, bass_m = chords[bar % 4]
        active_groove = bar >= 1 and (bar_t + bar_sec <= resolve_t + 0.4)

        add_stereo(bgm, bar_t, synth_pad_chord([midi_to_hz(m) for m in notes[:4]], 4.15 * beat, vel=0.14))
        for idx, m in enumerate(notes):
            add_stereo(bgm, bar_t + idx * 0.045, synth_epiano_note(midi_to_hz(m), 2.2 * beat, vel=0.22), pan=-0.35 + 0.17 * idx)
        if active_groove:
            for idx, m in enumerate(notes[1:]):
                add_stereo(bgm, bar_t + 2.5 * beat + idx * 0.03, synth_epiano_note(midi_to_hz(m), 1.4 * beat, vel=0.14), pan=0.25 - 0.15 * idx)
            add_stereo(bgm, bar_t, synth_bass(midi_to_hz(bass_m), 2.3 * beat, vel=0.26))
            add_stereo(bgm, bar_t + 2.5 * beat, synth_bass(midi_to_hz(bass_m + 7), 1.2 * beat, vel=0.17))
            for b_off, m in melody[bar % 4]:
                add_stereo(bgm, bar_t + b_off * beat, synth_pluck(midi_to_hz(m), 0.75, vel=0.23), pan=0.22 if b_off % 1 else -0.22)
            add_stereo(bgm, bar_t, kick, gain=0.82)
            add_stereo(bgm, bar_t + 2.5 * beat, kick, gain=0.68)
            add_stereo(bgm, bar_t + beat, synth_rim_click(rng), pan=-0.12, gain=0.75)
            add_stereo(bgm, bar_t + 3.0 * beat, synth_rim_click(rng), pan=0.12, gain=0.75)
            for eighth in range(8):
                is_open = eighth == 7 and (bar % 2 == 1)
                add_stereo(bgm, bar_t + eighth * 0.5 * beat, synth_soft_hat(rng, open_hat=is_open), pan=0.28 if eighth % 2 == 0 else -0.28, gain=0.72 if eighth % 2 == 0 else 0.52)
        bar += 1

    # Resolving Cmaj9 outro chord
    for i, m in enumerate([60, 64, 67, 71, 74, 79]):
        add_stereo(bgm, resolve_t + i * 0.055, synth_epiano_note(midi_to_hz(m), 3.6, vel=0.26), pan=-0.35 + 0.14 * i)
    add_stereo(bgm, resolve_t, synth_bass(midi_to_hz(48), 3.5, vel=0.24))

    bgm = add_stereo_reverb(bgm)
    fade_in_n = min(n, int(0.35 * SR))
    bgm[:fade_in_n] *= np.linspace(0.0, 1.0, fade_in_n)[:, None]
    fade_out_start = max(0, int((duration - 1.8) * SR))
    bgm[fade_out_start:] *= np.linspace(1.0, 0.0, n - fade_out_start)[:, None]

    # Apply event-driven UI SFX
    for ev in events:
        kind = ev.get("type")
        t = float(ev.get("t", 0.0))
        pan = float(ev.get("pan", 0.0))
        gain = float(ev.get("gain", 1.0))
        if kind == "whoosh":
            add_stereo(sfx, t, sfx_whoosh(rng, dur=float(ev.get("dur", 0.42)), up=bool(ev.get("up", True))), pan=pan, gain=gain)
        elif kind == "pop":
            add_stereo(sfx, t, sfx_ui_pop(float(ev.get("f0", 520.0)), float(ev.get("f1", 880.0)), float(ev.get("dur", 0.11))), pan=pan, gain=gain)
        elif kind == "chime":
            notes = [float(x) for x in ev.get("notes", [72, 76, 79])]
            add_stereo(sfx, t, sfx_chime(notes, step=float(ev.get("step", 0.06)), gain=float(ev.get("gain", 0.28))), pan=pan, gain=1.0)
        elif kind == "typing":
            count = int(ev.get("count", 16))
            dur = float(ev.get("dur", 1.4))
            for k in range(count):
                kt = t + k * (dur / max(1, count)) + (rng.random() - 0.5) * 0.014
                add_stereo(sfx, kt, sfx_key_tap(rng, 0.92 + 0.18 * rng.random()), pan=pan, gain=gain)

    mix = bgm + sfx
    peak = float(np.max(np.abs(mix))) if len(mix) else 0.0
    if peak > 0.0:
        mix = mix / max(peak, 0.95) * 0.88
    mix = np.tanh(mix * 1.05) / np.tanh(1.05) * 0.92
    return (mix * 32767.0).astype(np.int16)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Synthesize 48kHz stereo BGM + synced UI SFX WAV.\n"
            "Events JSON is a list of objects with keys: "
            "{type: 'whoosh'|'pop'|'chime'|'typing', t: seconds, ...}."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--duration", type=float, default=38.0, help="Total audio duration in seconds.")
    parser.add_argument("--bpm", type=float, default=112.0, help="BGM tempo in BPM (default: 112).")
    parser.add_argument("--outro-at", type=float, help="Timestamp for resolving outro chord (default: duration - 3.9).")
    parser.add_argument("--events", help="Path to JSON file listing synced SFX events.")
    parser.add_argument("--seed", type=int, default=20261128, help="Deterministic PRNG seed.")
    parser.add_argument("--out", required=True, help="Output WAV file path.")
    args = parser.parse_args()

    events = json.loads(Path(args.events).read_text()) if args.events else []
    pcm = render_audio(args.duration, args.bpm, args.outro_at, events, args.seed)
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(str(out_path), SR, pcm)
    print(f"Synthesized {out_path} ({args.duration:.1f}s, {SR}Hz stereo, {out_path.stat().st_size / 1024 / 1024:.2f} MB)")


if __name__ == "__main__":
    main()
