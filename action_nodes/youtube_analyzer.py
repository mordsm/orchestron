from base_node import ActionNode
import logging
import argparse
from pathlib import Path
import sys
import os
import yaml
from typing import Dict, Optional
from datetime import datetime
import json
import tempfile
import shutil

from dotenv import load_dotenv
from openai import OpenAI
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)
import yt_dlp

load_dotenv()


class YoutubeAnalyzerNode(ActionNode):
    """Node to analyze YouTube video transcript and metadata using OpenAI.

    Pipeline:
    1. Try to fetch transcript via youtube_transcript_api.
    2. If that fails, download audio with yt-dlp and transcribe via OpenAI.
    3. Summarize / analyze the resulting text.
    """

    @classmethod
    def get_parameters(cls):
        return {
            "parameters": [
                {"name": "url", "type": "string", "description": "YouTube video URL"},
                {
                    "name": "prompt",
                    "type": "string",
                    "description": "Prompt for OpenAI analysis",
                    "default": "Extract the main keypoints and important topics discussed in this video.",
                },
                {
                    "name": "max_length",
                    "type": "integer",
                    "description": "Max length of analysis output (tokens)",
                    "default": 500,
                },
                {
                    "name": "include_metadata",
                    "type": "boolean",
                    "description": "Include video metadata",
                    "default": True,
                },
                {
                    "name": "use_transcript",
                    "type": "boolean",
                    "description": "Use transcript if available",
                    "default": True,
                },
                {
                    "name": "language",
                    "type": "string",
                    "description": "Transcript language code (e.g., 'en')",
                    "default": "en",
                },
            ],
            "required": ["url"],
        }

    def __init__(self, config: Optional[Dict] = None, *args, **kwargs):
        super().__init__(config=config or {}, *args, **kwargs)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.client = OpenAI(api_key=self._get_api_key())

    # ---------- helpers ----------

    def _get_api_key(self) -> str:
        api_key = (
            self.config.get("openai_api_key")
            or os.getenv("OPENAI_API_KEY")
        )
        if not api_key:
            raise ValueError(
                "Missing openai_api_key in config and OPENAI_API_KEY env var not set"
            )
        return api_key

    def _extract_video_id(self, url: str) -> str:
        # handle standard watch URLs and youtu.be short URLs
        if "v=" in url:
            return url.split("v=")[1].split("&")[0]
        if "youtu.be/" in url:
            return url.split("youtu.be/")[1].split("?")[0]
        raise ValueError(f"Could not extract video_id from URL: {url}")

    def _fetch_transcript_via_api(self, video_id: str, language: str) -> str:
        """Try to get transcript via youtube_transcript_api.
        Returns empty string if not available.
        """
        try:
            segments = YouTubeTranscriptApi.get_transcript(
                video_id,
                languages=[language, "en"],
            )
            transcript_text = " ".join(item["text"] for item in segments)
            self.logger.info(
                f"Fetched transcript via YouTubeTranscriptApi for {video_id}, length={len(transcript_text)} chars"
            )
            return transcript_text
        except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as e:
            self.logger.warning(
                f"No usable transcript via API for {video_id}: {e}"
            )
            return ""
        except Exception as e:
            self.logger.error(
                f"Unexpected error while fetching transcript via API for {video_id}: {e}",
                exc_info=True,
            )
            return ""

    def _download_audio(self, url: str) -> str:
        """Download best audio with yt-dlp and return file path."""
        tmp_dir = tempfile.mkdtemp(prefix="yt_audio_")
        out_tmpl = os.path.join(tmp_dir, "audio.%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_tmpl,
            "quiet": True,
            "noprogress": True,
        }

        self.logger.info(f"Downloading audio for URL {url} into {tmp_dir}")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)
            self.logger.info(f"Downloaded audio file: {file_path}")
            return file_path
        except Exception as e:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            self.logger.error(f"Failed to download audio for {url}: {e}", exc_info=True)
            raise

    def _transcribe_audio(self, audio_path: str, language: str) -> str:
        """Transcribe audio file via OpenAI."""
        self.logger.info(f"Transcribing audio file: {audio_path}")
        try:
            with open(audio_path, "rb") as f:
                # adjust model name if needed in your account
                resp = self.client.audio.transcriptions.create(
                    model="gpt-4o-mini-transcribe",
                    file=f,
                    language=language,
                )
            text = resp.text
            self.logger.info(
                f"Transcription complete, length={len(text)} chars"
            )
            return text
        except Exception as e:
            self.logger.error(
                f"Failed to transcribe audio {audio_path}: {e}", exc_info=True
            )
            raise

    def _get_transcript(self, url: str, video_id: str, language: str, use_transcript: bool) -> str:
        """High-level transcript pipeline: API first, then audio+ASR."""
        if not use_transcript:
            return ""

        # 1) Try YouTubeTranscriptApi first
        transcript_text = self._fetch_transcript_via_api(video_id, language)
        if transcript_text:
            return transcript_text

        # 2) Fallback: download audio + transcribe
        try:
            audio_path = self._download_audio(url)
            tmp_dir = os.path.dirname(audio_path)
            try:
                transcript_text = self._transcribe_audio(audio_path, language)
                return transcript_text
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            # errors already logged inside helpers
            return ""

    def _analyze_text(
        self,
        analysis_text: str,
        prompt: str,
        max_length: int,
    ) -> str:
        """Call OpenAI to analyze/summarize the given text."""
        if not analysis_text.strip():
            analysis_text = "No transcript or description available. Only video title/metadata were provided."

        messages = [
            {
                "role": "system",
                "content": (
                    "You analyze videos only based on the text I provide to you "
                    "(title, description, transcript). "
                    "You do NOT access the raw video. "
                    "Even if the text is short or partial, you must still infer "
                    "likely keypoints, topics, and structure. "
                    "Never say that you cannot access or analyze the video; "
                    "always provide your best analysis from the given text."
                ),
            },
            {
                "role": "user",
                "content": f"{prompt}\n\nContent:\n{analysis_text[:4000]}",
            },
        ]

        resp = self.client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=max_length,
        )
        return resp.choices[0].message.content.strip()

    # ---------- main node API ----------

    def validate(self, **kwargs):
        super().validate(**kwargs)
        url = kwargs.get("url", "")
        if not (
            url.startswith("https://www.youtube.com/")
            or "youtu.be/" in url
        ):
            raise ValueError(f"Invalid YouTube URL: {url}")
        if kwargs.get("max_length", 0) <= 0:
            raise ValueError("max_length must be positive")

    def run(
        self,
        url: str,
        prompt: str = "Extract the main keypoints and important topics discussed in this video.",
        max_length: int = 500,
        include_metadata: bool = True,
        use_transcript: bool = True,
        language: str = "en",
    ) -> Dict:
        self.validate(
            url=url,
            prompt=prompt,
            max_length=max_length,
            include_metadata=include_metadata,
            use_transcript=use_transcript,
            language=language,
        )

        try:
            video_id = self._extract_video_id(url)
            self.logger.info(f"Analyzing YouTube video: {video_id}")

            # metadata placeholder – אפשר לחבר בעתיד ל־YouTube Data API
            metadata = {
                "title": "Unknown",
                "description": "Unknown",
                "channel": "Unknown",
                "video_id": video_id,
                "url": url,
            }
            try:
                # כרגע רק דוגמה: אתה יכול בהמשך להחליף ב־API אמיתי
                metadata["title"] = (
                    "Rick Astley - Never Gonna Give You Up (Official Video)"
                )
                self.logger.info(
                    f"Retrieved metadata for video: {metadata['title']}"
                )
            except Exception as e:
                self.logger.warning(f"Failed to fetch metadata: {e}")

            # fetch transcript via API or audio fallback
            transcript_text = self._get_transcript(
                url=url,
                video_id=video_id,
                language=language,
                use_transcript=use_transcript,
            )

            # prepare text for analysis
            analysis_text = transcript_text or metadata.get("description") or ""
            if not analysis_text.strip():
                self.logger.warning(
                    "No transcript or description available, using title only"
                )
                analysis_text = f"Video title: {metadata['title']}"

            analysis = self._analyze_text(
                analysis_text=analysis_text,
                prompt=prompt,
                max_length=max_length,
            )
            self.logger.info(f"Generated analysis: {len(analysis)} chars")

            result: Dict = {
                "analysis": analysis,
                "timestamp": datetime.now().isoformat(),
            }
            if include_metadata:
                result["metadata"] = metadata
            if transcript_text:
                result["transcript"] = transcript_text
            result["video_url"] = url

            return result

        except Exception as e:
            self.logger.error(f"Failed to analyze video {url}: {e}", exc_info=True)
            raise


# ---------- CLI for standalone debug ----------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="Analyze YouTube video transcript and metadata."
    )
    parser.add_argument("--config", type=str, help="Path to config YAML file")

    for param in YoutubeAnalyzerNode.get_parameters()["parameters"]:
        parser.add_argument(
            f"--{param['name']}",
            type=int
            if param["type"] == "integer"
            else bool
            if param["type"] == "boolean"
            else str,
            default=param.get("default"),
            required=param["name"]
            in YoutubeAnalyzerNode.get_parameters()["required"],
            help=param["description"],
        )

    is_debug = hasattr(sys, "gettrace") and sys.gettrace() is not None
    if is_debug and len(sys.argv) == 1:
        default_args = [
            "--url",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "--language",
            "en",
        ]
        sys.argv.extend(default_args)
        logging.warning(
            "Debug mode detected with no arguments. Using default args: %s",
            default_args,
        )

    args = parser.parse_args()

    config: Dict = {}
    if args.config and Path(args.config).exists():
        try:
            with open(args.config, "r", encoding="utf-8") as f:
                full_cfg = yaml.safe_load(f) or {}
                config = full_cfg.get("youtubeanalyzer", {})
        except yaml.YAMLError as e:
            logging.error(f"Failed to load config.yaml: {e}")
            sys.exit(1)

    node = YoutubeAnalyzerNode(config=config)

    logging.info("Parsed arguments: %s", vars(args))

    try:
        result = node.run(**vars(args))
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except ValueError as e:
        logging.error(f"Argument validation failed: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Failed to run node: {e}", exc_info=True)
        sys.exit(1)



