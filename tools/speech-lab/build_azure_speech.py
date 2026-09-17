#!/usr/bin/env python3
"""Build deterministic Azure zh-TW Speech A/B audio assets.

Required for live synthesis:
  AZURE_SPEECH_KEY
  AZURE_SPEECH_REGION

The source of truth remains cases.json. This builder produces full-phoneme and
partial-phoneme MP3s for the three zh-TW Neural voices and a manifest consumed
by tools/azure-speech-ab.html.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_CASES = ROOT / "cases.json"
DEFAULT_OUTPUT = ROOT / "generated"
VOICES = [
    "zh-TW-HsiaoChenNeural",
    "zh-TW-HsiaoYuNeural",
    "zh-TW-YunJheNeural",
]
MODES = ["partial", "full"]
OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
USER_AGENT = "hanzi-writing-lab-speech-ab/1.0"


def load_cases(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "hanzi-speech-ab-cases-v1":
        raise ValueError("Unsupported cases schema")
    for case in data.get("cases", []):
        text = case["text"]
        chars = "".join(token[0] for token in case["tokens"])
        if chars != text:
            raise ValueError(f"{case['id']}: token text mismatch: {chars!r} != {text!r}")
        for token in case["tokens"]:
            if len(token) < 2 or not token[1]:
                raise ValueError(f"{case['id']}: missing zhuyin for {token[0]}")
    return data


def body_for_mode(case: dict, mode: str) -> str:
    tokens = case["tokens"]
    if mode == "full":
        ph = " ".join(token[1] for token in tokens)
        return f'<phoneme alphabet="sapi" ph="{escape(ph, quote=True)}">{escape(case["text"])}</phoneme>'
    if mode == "partial":
        out: list[str] = []
        for token in tokens:
            char, zhuyin = token[0], token[1]
            force = bool(token[2]) if len(token) >= 3 else False
            if force:
                out.append(f'<phoneme alphabet="sapi" ph="{escape(zhuyin, quote=True)}">{escape(char)}</phoneme>')
            else:
                out.append(escape(char))
        return "".join(out)
    raise ValueError(f"Unknown mode: {mode}")


def make_ssml(case: dict, voice: str, mode: str, rate: str) -> str:
    body = body_for_mode(case, mode)
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="zh-TW">'
        f'<voice name="{escape(voice, quote=True)}">'
        f'<prosody rate="{escape(rate, quote=True)}">{body}</prosody>'
        '</voice></speak>'
    )


def digest_for(case: dict, voice: str, mode: str, rate: str) -> str:
    payload = {
        "text": case["text"],
        "tokens": case["tokens"],
        "voice": voice,
        "mode": mode,
        "rate": rate,
        "format": OUTPUT_FORMAT,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def synthesize(ssml: str, key: str, region: str, timeout: int = 45) -> bytes:
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    request = urllib.request.Request(
        url,
        data=ssml.encode("utf-8"),
        method="POST",
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def synthesize_with_retry(ssml: str, key: str, region: str, retries: int = 5) -> bytes:
    for attempt in range(retries):
        try:
            return synthesize(ssml, key, region)
        except urllib.error.HTTPError as exc:
            if exc.code not in (408, 429, 500, 502, 503, 504) or attempt == retries - 1:
                detail = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Azure TTS HTTP {exc.code}: {detail[:500]}") from exc
            retry_after = exc.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else min(8 * (attempt + 1), 30)
            print(f"retry HTTP {exc.code} after {wait:.1f}s", file=sys.stderr)
            time.sleep(wait)
        except urllib.error.URLError as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"Azure TTS network error: {exc}") from exc
            time.sleep(min(3 * (attempt + 1), 15))
    raise RuntimeError("unreachable")


def build(args: argparse.Namespace) -> int:
    data = load_cases(args.cases)
    cases = data["cases"]
    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    key = os.environ.get("AZURE_SPEECH_KEY", "").strip()
    region = os.environ.get("AZURE_SPEECH_REGION", "").strip()
    can_synthesize = bool(key and region) and not args.dry_run

    manifest = {
        "schema": "hanzi-speech-ab-manifest-v1",
        "builtAt": datetime.now(timezone.utc).isoformat(),
        "status": "generated" if can_synthesize else ("dry_run" if args.dry_run else "credentials_missing"),
        "outputFormat": OUTPUT_FORMAT,
        "rate": args.rate,
        "voices": VOICES,
        "modes": MODES,
        "caseCount": len(cases),
        "variantCountExpected": len(cases) * len(VOICES) * len(MODES),
        "variants": {},
    }

    generated = 0
    reused = 0
    last_request_at = 0.0

    for case in cases:
        case_entry = {"text": case["text"], "focus": case.get("focus", ""), "variants": {}}
        for voice in VOICES:
            case_entry["variants"][voice] = {}
            for mode in MODES:
                digest = digest_for(case, voice, mode, args.rate)
                rel = Path("audio") / voice / mode / f"{case['id']}-{digest}.mp3"
                dest = output / rel
                ssml = make_ssml(case, voice, mode, args.rate)
                item = {
                    "audio": str(Path("tools/speech-lab/generated") / rel).replace("\\", "/"),
                    "digest": digest,
                    "ssml": ssml,
                    "ready": dest.exists(),
                }
                if can_synthesize:
                    if dest.exists() and dest.stat().st_size > 500:
                        reused += 1
                    else:
                        elapsed = time.monotonic() - last_request_at
                        if elapsed < args.min_interval:
                            time.sleep(args.min_interval - elapsed)
                        audio = synthesize_with_retry(ssml, key, region)
                        last_request_at = time.monotonic()
                        if len(audio) < 500:
                            raise RuntimeError(f"{case['id']} {voice} {mode}: suspiciously small audio ({len(audio)} bytes)")
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(audio)
                        generated += 1
                    item["ready"] = True
                case_entry["variants"][voice][mode] = item
        manifest["variants"][case["id"]] = case_entry
        print(f"prepared {case['id']} {case['text']}")

    manifest["generatedNow"] = generated
    manifest["reused"] = reused
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": manifest["status"], "generated": generated, "reused": reused}, ensure_ascii=False))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--rate", default="0%", help="Azure SSML prosody rate, e.g. -10%%")
    parser.add_argument("--min-interval", type=float, default=float(os.environ.get("AZURE_TTS_MIN_INTERVAL", "3.2")))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(build(parse_args()))
