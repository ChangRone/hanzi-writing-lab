#!/usr/bin/env python3
"""Build production Hanzi Quiz audio with the accepted Azure Speech profile.

Decision:
  voice: zh-TW-HsiaoChenNeural
  mode: verified partial phoneme
  rate: -12%

The builder reads the public hanzi-quiz checkout, batches each pack into one
Azure PCM request separated by long SSML breaks, splits the PCM deterministically,
and writes one MP3 per question. Only Bopomofo pairs explicitly verified by the
A/B corpus are forced. Everything else is left to Azure context so that natural
tone sandhi and phrasing are preserved.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import http.client
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB_ROOT = HERE.parent.parent
DEFAULT_QUIZ = LAB_ROOT / ".cache" / "hanzi-quiz"
DEFAULT_OUT = LAB_ROOT / "production-audio" / "v1"
CASES = HERE / "cases.json"
VOICE = "zh-TW-HsiaoChenNeural"
MODE = "verified-partial"
RATE = "-12%"
PCM_FORMAT = "riff-24khz-16bit-mono-pcm"
MP3_BITRATE = "48k"
BREAK_MS = 2500
MIN_REQUEST_INTERVAL = float(os.environ.get("AZURE_TTS_MIN_INTERVAL", "3.2"))
USER_AGENT = "hanzi-writing-lab-production-speech/1.0"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def verified_pairs() -> set[tuple[str, str]]:
    data = load_json(CASES)
    pairs: set[tuple[str, str]] = set()
    for case in data.get("cases", []):
        for token in case.get("tokens", []):
            if len(token) >= 3 and token[2] is True:
                pairs.add((str(token[0]), str(token[1])))
    return pairs


def question_lesson_code(q: dict) -> str:
    qid = str(q.get("id", ""))
    return qid[8:10] if len(qid) == 12 and qid.isdigit() else "00"


def token_body(token: dict, force_pairs: set[tuple[str, str]]) -> str:
    ch = str(token.get("char", ""))
    zhuyin = str(token.get("zhuyin", ""))
    if ch and zhuyin and (ch, zhuyin) in force_pairs:
        return f'<phoneme alphabet="sapi" ph="{escape(zhuyin, quote=True)}">{escape(ch)}</phoneme>'
    return escape(ch)


def sentence_body(question: dict, force_pairs: set[tuple[str, str]]) -> str:
    tokens = question.get("tokens") or []
    chars = "".join(str(t.get("char", "")) for t in tokens)
    read_text = str(question.get("readText", ""))
    if chars != read_text:
        raise ValueError(f"{question.get('id')}: token text mismatch {chars!r} != {read_text!r}")
    return "".join(token_body(t, force_pairs) for t in tokens)


def make_ssml(questions: list[dict], force_pairs: set[tuple[str, str]]) -> str:
    pieces = []
    for idx, q in enumerate(questions):
        if idx:
            pieces.append(f'<break time="{BREAK_MS}ms"/>')
        pieces.append(sentence_body(q, force_pairs))
    body = "".join(pieces)
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="zh-TW">'
        f'<voice name="{VOICE}"><prosody rate="{RATE}">{body}</prosody></voice></speak>'
    )


def digest_question(q: dict, force_pairs: set[tuple[str, str]]) -> str:
    payload = {
        "id": str(q["id"]),
        "text": str(q["readText"]),
        "tokens": q["tokens"],
        "forced": sorted([list(x) for x in force_pairs if any(str(t.get("char","")) == x[0] and str(t.get("zhuyin","")) == x[1] for t in q["tokens"])]),
        "voice": VOICE,
        "mode": MODE,
        "rate": RATE,
        "format": "mp3-48k",
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def synthesize(ssml: str, key: str, region: str, timeout: int = 60) -> bytes:
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    req = urllib.request.Request(
        url,
        data=ssml.encode("utf-8"),
        method="POST",
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": PCM_FORMAT,
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def synthesize_retry(ssml: str, key: str, region: str, retries: int = 6) -> bytes:
    for attempt in range(retries):
        try:
            return synthesize(ssml, key, region)
        except urllib.error.HTTPError as exc:
            if exc.code not in (408, 429, 500, 502, 503, 504) or attempt == retries - 1:
                detail = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Azure TTS HTTP {exc.code}: {detail[:500]}") from exc
            retry_after = exc.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else min(8 * (attempt + 1), 40)
            print(f"retry HTTP {exc.code} after {wait:.1f}s", file=sys.stderr)
            time.sleep(wait)
        except (urllib.error.URLError, http.client.IncompleteRead) as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"Azure TTS network error: {exc}") from exc
            wait = min(3 * (attempt + 1), 20)
            print(f"retry network read after {wait:.1f}s: {type(exc).__name__}", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def pcm_samples(wav_bytes: bytes) -> tuple[wave._wave_params, array.array]:
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        tmp.write(wav_bytes)
        tmp.flush()
        with wave.open(tmp.name, "rb") as w:
            params = w.getparams()
            if params.nchannels != 1 or params.sampwidth != 2:
                raise RuntimeError(f"Unexpected PCM params: {params}")
            samples = array.array("h", w.readframes(params.nframes))
            if sys.byteorder != "little":
                samples.byteswap()
            return params, samples


def find_long_silences(samples: array.array, rate: int, expected: int) -> list[tuple[int, int]]:
    threshold = 48
    min_len = int(rate * 1.75)
    runs: list[tuple[int, int]] = []
    start = None
    for i, sample in enumerate(samples):
        if abs(sample) <= threshold:
            if start is None:
                start = i
        elif start is not None:
            if i - start >= min_len:
                runs.append((start, i))
            start = None
    if start is not None and len(samples) - start >= min_len:
        runs.append((start, len(samples)))
    # Ignore leading/trailing silence and take the longest interior runs.
    interior = [(a, b) for a, b in runs if a > rate // 2 and b < len(samples) - rate // 2]
    interior.sort(key=lambda x: x[1] - x[0], reverse=True)
    selected = sorted(interior[:expected])
    if len(selected) != expected:
        raise RuntimeError(f"Expected {expected} long SSML breaks, detected {len(selected)}")
    return selected


def trim_segment(samples: array.array, rate: int) -> array.array:
    threshold = 64
    first = 0
    last = len(samples)
    while first < last and abs(samples[first]) <= threshold:
        first += 1
    while last > first and abs(samples[last - 1]) <= threshold:
        last -= 1
    pad = int(rate * 0.12)
    first = max(0, first - pad)
    last = min(len(samples), last + pad)
    return samples[first:last]


def split_wav(wav_bytes: bytes, count: int) -> tuple[wave._wave_params, list[array.array]]:
    params, samples = pcm_samples(wav_bytes)
    if count == 1:
        return params, [trim_segment(samples, params.framerate)]
    breaks = find_long_silences(samples, params.framerate, count - 1)
    bounds = [0] + [(a + b) // 2 for a, b in breaks] + [len(samples)]
    chunks = [trim_segment(samples[bounds[i]:bounds[i + 1]], params.framerate) for i in range(count)]
    if any(len(x) < params.framerate // 3 for x in chunks):
        raise RuntimeError("Detected suspiciously short sentence chunk")
    return params, chunks


def write_mp3(params: wave._wave_params, samples: array.array, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        wav_path = Path(td) / "chunk.wav"
        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(params.framerate)
            raw = array.array("h", samples)
            if sys.byteorder != "little":
                raw.byteswap()
            w.writeframes(raw.tobytes())
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav_path), "-b:a", MP3_BITRATE, str(dest)],
            check=True,
        )
    if not dest.exists() or dest.stat().st_size < 500:
        raise RuntimeError(f"Invalid MP3 output: {dest}")


def load_questions(quiz_root: Path) -> tuple[list[tuple[str, list[dict]]], int]:
    catalog = load_json(quiz_root / "quiz-catalog-v2.json")
    included_urls = {str(x["dataUrl"]) for x in catalog["lessons"]}
    groups: list[tuple[str, list[dict]]] = []
    seen_ids: set[str] = set()
    total = 0
    for rel in sorted(included_urls):
        pack = load_json(quiz_root / rel)
        qs = [q for q in pack.get("questions", []) if q and isinstance(q.get("tokens"), list) and q.get("readText")]
        for q in qs:
            qid = str(q.get("id", ""))
            if not qid or qid in seen_ids:
                raise ValueError(f"Duplicate/missing question id: {qid!r}")
            seen_ids.add(qid)
        if qs:
            groups.append((rel, qs))
            total += len(qs)
    return groups, total


def existing_manifest(out: Path) -> dict:
    p = out / "manifest.json"
    if not p.exists():
        return {}
    try:
        return load_json(p)
    except Exception:
        return {}


def build(args: argparse.Namespace) -> int:
    quiz = args.quiz.resolve()
    out = args.output.resolve()
    force_pairs = verified_pairs()
    groups, total_questions = load_questions(quiz)
    previous = existing_manifest(out).get("questions", {})
    out.mkdir(parents=True, exist_ok=True)

    key = os.environ.get("AZURE_SPEECH_KEY", "").strip()
    region = os.environ.get("AZURE_SPEECH_REGION", "").strip()
    if not args.dry_run and not (key and region):
        raise RuntimeError("AZURE_SPEECH_KEY/AZURE_SPEECH_REGION are required")

    manifest = {
        "schema": "hanzi-quiz-production-audio-v1",
        "voice": VOICE,
        "mode": MODE,
        "rate": RATE,
        "sourceRepo": "ChangRone/hanzi-quiz",
        "questionCount": total_questions,
        "questions": {},
    }

    generated = 0
    reused = 0
    requests = 0
    last_request_at = 0.0

    for pack_index, (rel, questions) in enumerate(groups, 1):
        pending: list[dict] = []
        for q in questions:
            qid = str(q["id"])
            digest = digest_question(q, force_pairs)
            dest = out / "audio" / f"{qid}.mp3"
            old = previous.get(qid, {})
            ready = dest.exists() and dest.stat().st_size > 500 and old.get("digest") == digest
            manifest["questions"][qid] = {
                "text": str(q["readText"]),
                "digest": digest,
                "audio": f"production-audio/v1/audio/{qid}.mp3",
                "source": rel,
                "ready": bool(ready or not args.dry_run),
            }
            if ready:
                reused += 1
            else:
                pending.append(q)

        if pending and not args.dry_run:
            elapsed = time.monotonic() - last_request_at
            if requests and elapsed < args.min_interval:
                time.sleep(args.min_interval - elapsed)
            ssml = make_ssml(pending, force_pairs)
            wav_bytes = synthesize_retry(ssml, key, region)
            last_request_at = time.monotonic()
            requests += 1
            params, chunks = split_wav(wav_bytes, len(pending))
            for q, chunk in zip(pending, chunks):
                dest = out / "audio" / f"{q['id']}.mp3"
                write_mp3(params, chunk, dest)
                generated += 1
                manifest["questions"][str(q["id"])]["ready"] = True

        print(f"[{pack_index}/{len(groups)}] {rel}: pending={len(pending)}")

    manifest["generatedNow"] = generated
    manifest["reused"] = reused
    manifest["azureRequests"] = requests
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not args.dry_run:
        ready = [x for x in manifest["questions"].values() if x["ready"]]
        if len(ready) != total_questions:
            raise RuntimeError(f"Only {len(ready)}/{total_questions} audio files ready")
    print(json.dumps({"questions": total_questions, "generated": generated, "reused": reused, "requests": requests, "dryRun": args.dry_run}, ensure_ascii=False))
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--quiz", type=Path, default=DEFAULT_QUIZ)
    p.add_argument("--output", type=Path, default=DEFAULT_OUT)
    p.add_argument("--min-interval", type=float, default=MIN_REQUEST_INTERVAL)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    raise SystemExit(build(parse_args()))
