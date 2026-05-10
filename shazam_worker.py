#!/usr/bin/env python3
"""
shazam_worker.py — ShazamIO worker for TRACKR
Usage: python3 shazam_worker.py <path_to_audio_file>
Outputs JSON to stdout.
"""

import sys
import json
import asyncio
import os
import subprocess

# Принудительно UTF-8 на Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def err(msg):
    print(json.dumps({"error": msg}, ensure_ascii=False), flush=True)
    sys.exit(1)

try:
    from shazamio import Shazam
except ImportError:
    err("ShazamIO не установлен. Выполните: pip install shazamio")

def find_ffmpeg():
    """Ищем ffmpeg в PATH и стандартных местах установки winget/choco."""
    try:
        r = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        if r.returncode == 0:
            return 'ffmpeg'
    except Exception:
        pass

    candidates = [
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        r'C:\ffmpeg\bin\ffmpeg.exe',
        r'C:\ProgramData\chocolatey\bin\ffmpeg.exe',
    ]

    local_app = os.environ.get('LOCALAPPDATA', '')
    if local_app:
        winget_base = os.path.join(local_app, 'Microsoft', 'WinGet', 'Packages')
        if os.path.isdir(winget_base):
            for entry in os.listdir(winget_base):
                if 'ffmpeg' in entry.lower():
                    for root, dirs, files in os.walk(os.path.join(winget_base, entry)):
                        if 'ffmpeg.exe' in files:
                            candidates.append(os.path.join(root, 'ffmpeg.exe'))

    for c in candidates:
        if os.path.isfile(c):
            return c

    return None

async def recognize(file_path: str):
    if not os.path.exists(file_path):
        err(f"Файл не найден: {file_path}")

    ffmpeg = find_ffmpeg()
    converted_path = file_path.rsplit('.', 1)[0] + '_conv.mp3'
    target = file_path

    if ffmpeg:
        try:
            proc = subprocess.run(
                [ffmpeg, '-y', '-i', file_path, '-ar', '44100', '-ac', '1', '-b:a', '128k', converted_path],
                capture_output=True, timeout=30
            )
            if os.path.exists(converted_path) and os.path.getsize(converted_path) > 1000:
                target = converted_path
                sys.stderr.write(f"DEBUG: конвертация OK -> {converted_path}\n")
            else:
                sys.stderr.write("DEBUG: конвертация не удалась, пробуем оригинал\n")
        except Exception as e:
            sys.stderr.write(f"DEBUG: ffmpeg ошибка: {e}\n")
    else:
        sys.stderr.write("DEBUG: ffmpeg не найден, пробуем оригинал\n")

    sys.stderr.write(f"DEBUG: target={target}, size={os.path.getsize(target)} bytes\n")
    sys.stderr.flush()

    shazam = Shazam()
    try:
        result = await shazam.recognize(target)
    except Exception as e:
        err(f"Ошибка ShazamIO: {str(e)}")
    finally:
        if os.path.exists(converted_path):
            try:
                os.unlink(converted_path)
            except Exception:
                pass

    track = result.get("track")
    if not track:
        print(json.dumps({"notFound": True}), flush=True)
        return

    # Parse metadata
    sections = track.get("sections", [])
    meta_section = next((s for s in sections if s.get("type") == "SONG"), {})
    meta = {m["title"]: m.get("text", "") for m in meta_section.get("metadata", [])}

    # Cover image
    images = track.get("images", {})
    cover = images.get("coverarthq") or images.get("coverart") or ""

    # Preview URL (30-sec mp3 sample)
    hub = track.get("hub", {})
    preview_url = ""
    for a in hub.get("actions", []):
        if a.get("type") == "uri" and a.get("uri", "").endswith(".mp3"):
            preview_url = a["uri"]
            break
    if not preview_url:
        for opt in hub.get("options", []):
            for a in opt.get("actions", []):
                uri = a.get("uri", "")
                if uri.endswith(".mp3") or "preview" in uri.lower():
                    preview_url = uri
                    break
            if preview_url:
                break

    # Streaming links
    providers = hub.get("providers", [])
    spotify_url = ""
    apple_url = ""
    for p in providers:
        ptype = p.get("type", "").lower()
        uri = next((a.get("uri", "") for a in p.get("actions", []) if a.get("uri")), "")
        if "spotify" in ptype and uri:
            spotify_url = uri
        if "applemusic" in ptype and uri:
            apple_url = uri

    for opt in hub.get("options", []):
        for action in opt.get("actions", []):
            uri = action.get("uri", "")
            if "spotify" in uri and not spotify_url:
                spotify_url = uri
            if "apple" in uri and not apple_url:
                apple_url = uri

    out = {
        "title":      track.get("title", ""),
        "artist":     track.get("subtitle", ""),
        "album":      meta.get("Album", ""),
        "year":       meta.get("Released", ""),
        "label":      meta.get("Label", ""),
        "isrc":       track.get("isrc", ""),
        "cover":      cover,
        "previewUrl": preview_url,
        "spotifyUrl": spotify_url,
        "appleUrl":   apple_url,
        "confidence": 95,
    }

    print(json.dumps(out, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        err("Использование: python3 shazam_worker.py <audio_file>")
    asyncio.run(recognize(sys.argv[1]))