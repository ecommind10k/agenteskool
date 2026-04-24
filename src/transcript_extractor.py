"""
Transcript extractor for Skool lessons.

Strategy (in order of preference):
1. Wistia data API  — returns captions/transcript JSON (fast, no download)
2. yt-dlp subtitles — tries to pull embedded subs from the video URL
3. Whisper fallback — downloads audio and runs local speech-to-text
"""

import asyncio
import json
import re
import tempfile
import os
from pathlib import Path
from typing import Optional

import httpx


class TranscriptExtractor:
    """Extract transcript text from a video using multiple strategies."""

    WISTIA_DATA_URL = "https://fast.wistia.net/embed/medias/{media_id}.json"

    def __init__(self, whisper_model: str = "base"):
        self.whisper_model = whisper_model
        self._whisper = None  # Lazy-loaded

    # ------------------------------------------------------------------ #
    # Public entry point                                                   #
    # ------------------------------------------------------------------ #

    async def extract(
        self,
        wistia_id: Optional[str] = None,
        video_url: Optional[str] = None,
        lesson_description: str = "",
    ) -> str:
        """
        Return transcript text. Falls back gracefully through strategies.
        If all fail, returns the lesson description (better than nothing).
        """
        transcript = ""

        if wistia_id:
            transcript = await self._from_wistia(wistia_id)

        if not transcript and video_url:
            transcript = await self._from_yt_dlp(video_url)

        if not transcript and (wistia_id or video_url):
            print("    [Transcript] Trying Whisper fallback (downloads audio)...")
            transcript = await self._from_whisper(wistia_id, video_url)

        if not transcript:
            print("    [Transcript] No transcript found; using lesson description.")
            transcript = lesson_description

        return transcript

    # ------------------------------------------------------------------ #
    # Strategy 1: Wistia data API                                         #
    # ------------------------------------------------------------------ #

    async def _from_wistia(self, media_id: str) -> str:
        url = self.WISTIA_DATA_URL.format(media_id=media_id)
        print(f"    [Transcript] Fetching Wistia data for {media_id}...")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return ""
                data = resp.json()
                return self._parse_wistia_json(data)
        except Exception as e:
            print(f"    [Transcript] Wistia API error: {e}")
            return ""

    def _parse_wistia_json(self, data: dict) -> str:
        """
        Extract captions from Wistia media JSON.
        The captions live at data.media.captions[].englishName / .text
        or in the timedTextTracks assets.
        """
        try:
            media = data.get("media", {})

            # Newer Wistia format: captions array
            captions = media.get("captions", [])
            for cap in captions:
                text = cap.get("text", "")
                if text:
                    return self._clean_vtt(text)

            # Older format: assets with type "captions"
            assets = media.get("assets", [])
            for asset in assets:
                if "caption" in asset.get("type", "").lower():
                    url = asset.get("url", "")
                    if url:
                        return self._fetch_caption_file_sync(url)

            # Try timedTextTracks (another Wistia variant)
            tracks = media.get("timedTextTracks", [])
            for track in tracks:
                if track.get("kind") == "captions":
                    src = track.get("src", "")
                    if src:
                        return self._fetch_caption_file_sync(src)

        except Exception as e:
            print(f"    [Transcript] Error parsing Wistia JSON: {e}")

        return ""

    def _fetch_caption_file_sync(self, url: str) -> str:
        try:
            import requests
            resp = requests.get(url, timeout=20)
            return self._clean_vtt(resp.text)
        except Exception:
            return ""

    def _clean_vtt(self, vtt: str) -> str:
        """Strip VTT/SRT timing headers and return plain text."""
        lines = []
        for line in vtt.splitlines():
            line = line.strip()
            # Skip VTT header, blank lines, and timestamp lines
            if not line:
                continue
            if line.startswith("WEBVTT") or line.startswith("NOTE"):
                continue
            if re.match(r'^\d+$', line):  # SRT sequence numbers
                continue
            if re.match(r'\d{2}:\d{2}', line):  # timestamp
                continue
            # Remove inline tags like <c>, <00:01:02.000>
            line = re.sub(r'<[^>]+>', '', line)
            if line:
                lines.append(line)
        return " ".join(lines)

    # ------------------------------------------------------------------ #
    # Strategy 2: yt-dlp subtitles                                        #
    # ------------------------------------------------------------------ #

    async def _from_yt_dlp(self, url: str) -> str:
        print(f"    [Transcript] Trying yt-dlp subtitles for {url[:60]}...")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                cmd = (
                    f'yt-dlp --skip-download --write-auto-subs --write-subs '
                    f'--sub-format vtt --output "{tmpdir}/sub" "{url}" 2>&1'
                )
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=60)

                # Find any .vtt file created
                vtt_files = list(Path(tmpdir).glob("*.vtt"))
                if vtt_files:
                    text = vtt_files[0].read_text(encoding="utf-8", errors="ignore")
                    cleaned = self._clean_vtt(text)
                    if cleaned:
                        print("    [Transcript] Got subtitles via yt-dlp.")
                        return cleaned
        except Exception as e:
            print(f"    [Transcript] yt-dlp error: {e}")
        return ""

    # ------------------------------------------------------------------ #
    # Strategy 3: Whisper (download audio → transcribe locally)           #
    # ------------------------------------------------------------------ #

    async def _from_whisper(
        self,
        wistia_id: Optional[str],
        video_url: Optional[str],
    ) -> str:
        try:
            audio_path = await self._download_audio(wistia_id, video_url)
            if not audio_path:
                return ""

            print(f"    [Transcript] Running Whisper ({self.whisper_model}) on audio...")
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(None, self._whisper_transcribe, audio_path)
            Path(audio_path).unlink(missing_ok=True)
            return text
        except Exception as e:
            print(f"    [Transcript] Whisper error: {e}")
            return ""

    async def _download_audio(
        self,
        wistia_id: Optional[str],
        video_url: Optional[str],
    ) -> Optional[str]:
        """Download audio track using yt-dlp; returns path to audio file."""
        target_url = video_url
        if wistia_id:
            target_url = f"https://fast.wistia.net/embed/medias/{wistia_id}"
        if not target_url:
            return None

        tmpfile = tempfile.mktemp(suffix=".mp3")
        cmd = (
            f'yt-dlp -x --audio-format mp3 --audio-quality 5 '
            f'-o "{tmpfile}" "{target_url}" 2>&1'
        )
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=300)
            if Path(tmpfile).exists():
                return tmpfile
        except Exception as e:
            print(f"    [Transcript] Audio download failed: {e}")
        return None

    def _whisper_transcribe(self, audio_path: str) -> str:
        if self._whisper is None:
            import whisper
            print(f"    [Transcript] Loading Whisper model '{self.whisper_model}'...")
            self._whisper = whisper.load_model(self.whisper_model)
        result = self._whisper.transcribe(audio_path, fp16=False)
        return result.get("text", "")
