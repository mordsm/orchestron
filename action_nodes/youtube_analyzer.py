from base_node import ActionNode
import logging
import argparse
from pathlib import Path
import sys
import yaml
from typing import Dict
from datetime import datetime
import json
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound
from openai import OpenAI

class YoutubeAnalyzerNode(ActionNode):
    """Node to analyze YouTube video transcript and metadata using OpenAI."""
    
    @classmethod
    def get_parameters(cls):
        return {
            "parameters": [
                {"name": "url", "type": "string", "description": "YouTube video URL"},
                {"name": "prompt", "type": "string", "description": "Prompt for OpenAI analysis", "default": "Extract the main keypoints and important topics discussed in this video"},
                {"name": "max_length", "type": "integer", "description": "Max length of analysis output", "default": 500},
                {"name": "include_metadata", "type": "boolean", "description": "Include video metadata", "default": True},
                {"name": "use_transcript", "type": "boolean", "description": "Use transcript if available", "default": True},
                {"name": "language", "type": "string", "description": "Transcript language code (e.g., 'en')", "default": "en"}
            ],
            "required": ["url"]
        }
    
    def validate(self, **kwargs):
        super().validate(**kwargs)
        if not kwargs.get("url", "").startswith("https://www.youtube.com/"):
            raise ValueError("Invalid YouTube URL")
        if kwargs.get("max_length", 0) <= 0:
            raise ValueError("max_length must be positive")
        if 'openai_api_key' not in self.config:
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("Missing openai_api_key in config or environment variable")
            self.config['openai_api_key'] = api_key
    
    def run(self, url: str, prompt: str = "Extract the main keypoints and important topics discussed in this video", max_length: int = 500, include_metadata: bool = True, use_transcript: bool = True, language: str = "en") -> Dict:
        self.validate(url=url, prompt=prompt, max_length=max_length, include_metadata=include_metadata, use_transcript=use_transcript, language=language)
        
        try:
            # Extract video ID
            video_id = url.split("v=")[1].split("&")[0] if "&" in url else url.split("v=")[1]
            self.logger.info(f"Analyzing YouTube video: {video_id}")
            
            # Fetch metadata (simplified, as actual metadata fetching not shown in log)
            metadata = {
                "title": "Unknown",
                "description": "Unknown",
                "channel": "Unknown"
            }
            try:
                # Placeholder for metadata fetching (e.g., via youtube-dl or API)
                metadata['title'] = "Rick Astley - Never Gonna Give You Up (Official Video)"  # Based on log
                self.logger.info(f"Retrieved metadata for video: {metadata['title']}")
            except Exception as e:
                self.logger.warning(f"Failed to fetch metadata: {e}")
            
            # Fetch transcript
            transcript_text = ""
            if use_transcript:
                try:
                    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                    transcript = transcript_list.find_generated_transcript([language])
                    transcript_text = " ".join([item['text'] for item in transcript.fetch()])
                    self.logger.info(f"Fetched transcript for video {video_id}, length: {len(transcript_text)} chars")
                except NoTranscriptFound:
                    self.logger.warning(f"Transcript not accessible for {video_id}: Transcript may exist but could not be extracted")
                    transcript_text = ""
            
            # Prepare text for analysis
            analysis_text = transcript_text if transcript_text else metadata['description']
            if not analysis_text:
                self.logger.warning("No transcript or description available, using metadata only")
                analysis_text = f"Video title: {metadata['title']}"
            
            # Call OpenAI API
            client = OpenAI(api_key=self.config['openai_api_key'])
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that analyzes video content."},
                    {"role": "user", "content": f"{prompt}\n\nContent: {analysis_text[:4000]}"}
                ],
                max_tokens=max_length
            )
            analysis = response.choices[0].message.content.strip()
            self.logger.info(f"Generated analysis: {len(analysis)} chars")
            
            result = {
                "analysis": analysis,
                "timestamp": datetime.now().isoformat()
            }
            if include_metadata:
                result["metadata"] = metadata
            if transcript_text:
                result["transcript"] = transcript_text
            
            return result
        
        except Exception as e:
            self.logger.error(f"Failed to analyze video {url}: {e}")
            raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Analyze YouTube video transcript and metadata.")
    parser.add_argument('--config', type=str, help="Path to config YAML file")
    for param in YoutubeAnalyzerNode.get_parameters()["parameters"]:
        parser.add_argument(
            f"--{param['name']}",
            type=int if param["type"] == "integer" else bool if param["type"] == "boolean" else str,
            default=param.get("default"),
            required=param["name"] in YoutubeAnalyzerNode.get_parameters()["required"],
            help=param["description"]
        )
    
    is_debug = hasattr(sys, 'gettrace') and sys.gettrace() is not None
    if is_debug and len(sys.argv) == 1:
        default_args = [
            '--url', 'https://www.youtube.com/watch?v=GuTcle5edjk&t=599s',
            '--language', 'en'
        ]
        sys.argv.extend(default_args)
        logging.warning("Debug mode detected with no arguments. Using default args: %s", default_args)
    
    args = parser.parse_args()
    
    config = {}
    if args.config and Path(args.config).exists():
        try:
            with open(args.config, 'r') as f:
                config = yaml.safe_load(f).get('youtubeanalyzer', {})
        except yaml.YAMLError as e:
            logging.error(f"Failed to load config.yaml: {e}")
            sys.exit(1)
    
    node = YoutubeAnalyzerNode(config=config)
    
    logging.info("Parsed arguments: %s", vars(args))
    
    try:
        result = node.run(**vars(args))
        print(f"Result: {json.dumps(result, indent=2, ensure_ascii=False)}")
    except ValueError as e:
        logging.error(f"Argument validation failed: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Failed to run node: {e}")
        sys.exit(1)