import os
import argparse
import yaml
from pathlib import Path
import sys
import logging
from typing import Dict, List, Optional
import requests
import re
from base_node import ActionNode

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    # Test if the main method exists
    if hasattr(YouTubeTranscriptApi, 'get_transcript'):
        TRANSCRIPT_AVAILABLE = True
    else:
        TRANSCRIPT_AVAILABLE = False
        logging.warning("youtube-transcript-api installed but methods not available")
except ImportError:
    TRANSCRIPT_AVAILABLE = False
    YouTubeTranscriptApi = None
    logging.warning("youtube-transcript-api not available. Install with: pip install youtube-transcript-api")

class YouTubeAnalyzerNode(ActionNode):
    """Node to analyze YouTube videos and extract keypoints or custom analysis. Config: {'youtube_api_key', 'openai_api_key'}."""
    
    @classmethod
    def get_parameters(cls):
        return {
            "parameters": [
                {"name": "url", "type": "string", "description": "YouTube video URL", "required": True},
                {"name": "prompt", "type": "string", "description": "Custom analysis prompt", "default": "Extract the main keypoints and important topics discussed in this video"},
                {"name": "max_length", "type": "integer", "description": "Maximum response length in words", "default": 500},
                {"name": "include_metadata", "type": "boolean", "description": "Include video metadata in response", "default": True},
                {"name": "use_transcript", "type": "boolean", "description": "Try to use video transcript for analysis", "default": True},
                {"name": "language", "type": "string", "description": "Preferred transcript language (e.g., 'en', 'es')", "default": "en"}
            ],
            "required": ["url"]
        }
    
    def validate(self, **kwargs):
        super().validate(**kwargs)
        
        # Check required config
        required_config = {'youtube_api_key', 'openai_api_key'}
        missing = required_config - set(self.config.keys())
        if missing:
            env_vars = {
                'youtube_api_key': os.getenv('YOUTUBE_API_KEY'),
                'openai_api_key': os.getenv('OPENAI_API_KEY')
            }
            for key in missing:
                if env_vars[key] is None or env_vars[key].strip() == '':
                    raise ValueError(f"Missing or empty required config: {key}. Set in config.yaml or environment variable.")
                self.config[key] = env_vars[key]
        
        # Validate parameters
        url = kwargs.get('url')
        if url and not self._is_valid_youtube_url(url):
            raise ValueError("Invalid YouTube URL format")
        
        max_length = kwargs.get('max_length')
        if max_length is not None and max_length <= 0:
            raise ValueError("max_length must be positive")
    
    def _is_valid_youtube_url(self, url: str) -> bool:
        """Validate if the URL is a valid YouTube URL."""
        youtube_patterns = [
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]+)',
            r'(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]+)',
            r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]+)'
        ]
        return any(re.match(pattern, url) for pattern in youtube_patterns)
    
    def _extract_video_id(self, url: str) -> str:
        """Extract video ID from YouTube URL."""
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        raise ValueError("Could not extract video ID from URL")
    
    def _get_video_metadata(self, video_id: str) -> Dict:
        """Fetch video metadata from YouTube API."""
        api_key = self.config['youtube_api_key']
        url = f"https://www.googleapis.com/youtube/v3/videos"
        params = {
            'part': 'snippet,statistics,contentDetails',
            'id': video_id,
            'key': api_key
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        if not data.get('items'):
            raise ValueError("Video not found or not accessible")
        
        item = data['items'][0]
        snippet = item['snippet']
        statistics = item.get('statistics', {})
        content_details = item.get('contentDetails', {})
        
        return {
            'title': snippet.get('title'),
            'description': snippet.get('description'),
            'channel_title': snippet.get('channelTitle'),
            'published_at': snippet.get('publishedAt'),
            'duration': content_details.get('duration'),
            'view_count': statistics.get('viewCount'),
            'like_count': statistics.get('likeCount'),
            'comment_count': statistics.get('commentCount'),
            'tags': snippet.get('tags', [])
        }
    
    def _get_video_transcript_enhanced(self, video_id: str, language: str = 'en') -> Dict[str, str]:
        """
        Enhanced transcript fetching with multiple fallback methods.
        """
        if not TRANSCRIPT_AVAILABLE or YouTubeTranscriptApi is None:
            return {
                'text': "Transcript API not available.",
                'source': 'error'
            }
        
        # Method 1: Try youtube-transcript-api with multiple approaches
        try:
            # Approach 1: Direct get_transcript with specified language
            try:
                transcript_data = YouTubeTranscriptApi.get_transcript(video_id, languages=[language])
                full_text = ' '.join([entry.get('text', '') for entry in transcript_data])
                if full_text.strip():
                    return {'text': full_text, 'source': f'api-direct-{language}'}
            except Exception as e1:
                self.logger.debug(f"Direct get_transcript with {language} failed: {e1}")
            
            # Approach 2: Try with different language codes
            for lang_code in ['en', 'en-US', 'en-GB', 'auto', language]:
                if lang_code == language:
                    continue  # Already tried above
                try:
                    transcript_data = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang_code])
                    full_text = ' '.join([entry.get('text', '') for entry in transcript_data])
                    if full_text.strip():
                        return {'text': full_text, 'source': f'api-lang-{lang_code}'}
                except Exception:
                    continue
            
            # Approach 3: Try list_transcripts method (most comprehensive)
            try:
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                
                # First try to find manually created transcripts
                try:
                    for transcript in transcript_list:
                        if hasattr(transcript, 'is_generated') and not transcript.is_generated:
                            try:
                                transcript_data = transcript.fetch()
                                full_text = ' '.join([entry.get('text', '') for entry in transcript_data])
                                if full_text.strip():
                                    return {'text': full_text, 'source': f'api-manual-{transcript.language_code}'}
                            except Exception:
                                continue
                except AttributeError:
                    pass  # is_generated attribute might not exist in all versions
                
                # Then try any available transcript
                for transcript in transcript_list:
                    try:
                        transcript_data = transcript.fetch()
                        full_text = ' '.join([entry.get('text', '') for entry in transcript_data])
                        if full_text.strip():
                            lang_code = getattr(transcript, 'language_code', 'unknown')
                            return {'text': full_text, 'source': f'api-list-{lang_code}'}
                    except Exception:
                        continue
                        
            except Exception as e3:
                self.logger.debug(f"list_transcripts failed: {e3}")
            
            # Approach 4: Try without language specification
            try:
                transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
                full_text = ' '.join([entry.get('text', '') for entry in transcript_data])
                if full_text.strip():
                    return {'text': full_text, 'source': 'api-no-lang'}
            except Exception as e4:
                self.logger.debug(f"No-language get_transcript failed: {e4}")
                
        except Exception as e:
            self.logger.debug(f"All youtube-transcript-api methods failed: {e}")
        
        # Final fallback
        error_msg = "Transcript may exist but could not be extracted due to API limitations"
        self.logger.info(f"Transcript not accessible for {video_id}: {error_msg}")
        return {
            'text': f"Transcript appears to be available but could not be extracted ({error_msg}). Analysis will use video metadata instead.",
            'source': 'unavailable'
        }
    
    def _format_transcript_info(self, transcript_result: Dict[str, str]) -> str:
        """Format transcript information for the analysis content."""
        if transcript_result['source'] in ['error', 'unavailable']:
            return f"\n\nTranscript Status: {transcript_result['text']}"
        else:
            # Limit transcript length and clean it up
            transcript_text = transcript_result['text'][:8000]  # Limit to ~8000 chars
            # Clean up common transcript artifacts
            transcript_text = transcript_text.replace('[Music]', '').replace('[Applause]', '')
            transcript_text = transcript_text.replace('  ', ' ')  # Clean up double spaces
            transcript_text = ' '.join(transcript_text.split())  # Clean up whitespace
            return f"\n\nTranscript ({transcript_result['source']}):\n{transcript_text}"
    
    def _analyze_with_openai(self, content: str, prompt: str, max_length: int) -> str:
        """Analyze content using OpenAI API."""
        api_key = self.config['openai_api_key']
        
        system_prompt = f"""You are a helpful assistant that analyzes video content. 
        Please provide a response that is approximately {max_length} words or less.
        Be concise but comprehensive in your analysis. Focus on the most important and relevant information."""
        
        user_prompt = f"""
        {prompt}
        
        Video Content:
        {content}
        """
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': 'gpt-3.5-turbo',
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            'max_tokens': min(max_length * 2, 4000),  # Rough estimate for token limit
            'temperature': 0.7
        }
        
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers=headers,
            json=data
        )
        response.raise_for_status()
        
        result = response.json()
        return result['choices'][0]['message']['content'].strip()
    
    def run(self, url: str, prompt: str = None, max_length: int = 500, 
            include_metadata: bool = True, use_transcript: bool = True, 
            language: str = 'en') -> Dict:
        """Run the YouTube analysis with enhanced transcript handling."""
        self.validate(url=url, prompt=prompt, max_length=max_length, 
                     include_metadata=include_metadata, use_transcript=use_transcript)
        
        if prompt is None:
            prompt = "Extract the main keypoints and important topics discussed in this video"
        
        try:
            # Extract video ID
            video_id = self._extract_video_id(url)
            self.logger.info(f"Analyzing YouTube video: {video_id}")
            
            # Get video metadata
            metadata = self._get_video_metadata(video_id)
            self.logger.info(f"Retrieved metadata for video: {metadata['title']}")
            
            # Prepare content for analysis
            analysis_content = f"""
            Title: {metadata['title']}
            Channel: {metadata['channel_title']}
            Published: {metadata['published_at']}
            Duration: {metadata['duration']}
            Views: {metadata.get('view_count', 'N/A')}
            Tags: {', '.join(metadata['tags'][:10]) if metadata['tags'] else 'None'}
            Description: {metadata['description'][:1500] if metadata['description'] else 'No description'}
            """
            
            # Handle transcript automatically
            transcript_info = None
            if use_transcript:
                # Try to get transcript automatically using enhanced method
                transcript_result = self._get_video_transcript_enhanced(video_id, language)
                transcript_info = {
                    'available': transcript_result['source'] not in ['error', 'unavailable'],
                    'source': transcript_result['source']
                }
                
                if transcript_info['available']:
                    transcript_content = self._format_transcript_info(transcript_result)
                    analysis_content += transcript_content
                    transcript_info['length'] = len(transcript_result['text'])
                    self.logger.info(f"Using transcript from source: {transcript_result['source']}")
                else:
                    analysis_content += f"\n\n{transcript_result['text']}"
                    self.logger.warning("Transcript not available, using metadata only")
            
            # Analyze with AI
            analysis = self._analyze_with_openai(analysis_content, prompt, max_length)
            
            # Determine analysis method
            if transcript_info and transcript_info['available']:
                analysis_method = "metadata_and_transcript"
            else:
                analysis_method = "metadata_only"
            
            # Prepare result
            result = {
                "video_id": video_id,
                "video_url": url,
                "analysis": analysis,
                "prompt_used": prompt,
                "analysis_method": analysis_method
            }
            
            if include_metadata:
                result["metadata"] = metadata
            
            if transcript_info:
                result["transcript_info"] = transcript_info
            
            self.logger.info(f"Successfully analyzed video: {video_id} using {analysis_method}")
            return result
            
        except requests.RequestException as e:
            self.logger.error(f"API request failed: {e}")
            raise ValueError(f"Failed to fetch data from API: {e}")
        except Exception as e:
            self.logger.error(f"Failed to analyze video: {e}")
            raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze YouTube videos standalone.")
    parser.add_argument('--config', type=str, help="Path to config YAML file")
    
    # Add parameters from get_parameters
    for param in YouTubeAnalyzerNode.get_parameters()["parameters"]:
        param_type = str
        if param["type"] == "integer":
            param_type = int
        elif param["type"] == "boolean":
            param_type = lambda x: x.lower() in ('true', '1', 'yes', 'on')
        
        parser.add_argument(
            f"--{param['name']}",
            type=param_type,
            default=param.get("default"),
            help=param["description"],
            required=param.get("required", False)
        )
    
    # Debug mode handling
    is_debug = hasattr(sys, 'gettrace') and sys.gettrace() is not None
    if is_debug and len(sys.argv) == 1:
        default_args = [
            '--url', 'https://www.youtube.com/watch?v=GuTcle5edjk',
            '--prompt', 'What are the main themes and messages in this video?',
            '--max_length', '300',
            '--config', 'config.yaml'
        ]
        sys.argv.extend(default_args)
        logging.warning("Debug mode detected with no arguments. Using default args: %s", default_args)
    
    args = parser.parse_args()
    
    # Load config
    config = {}
    if args.config and Path(args.config).exists():
        try:
            with open(args.config, 'r') as f:
                full_config = yaml.safe_load(f)
                config = full_config.get('youtubeanalyzer', {})
        except yaml.YAMLError as e:
            logging.error(f"Failed to load config.yaml: {e}")
            sys.exit(1)
    
    # Create and run node
    node = YouTubeAnalyzerNode(config=config)
    
    logging.info("Parsed arguments: %s", vars(args))
    
    try:
        # Remove config from args before passing to run
        run_args = {k: v for k, v in vars(args).items() if k != 'config'}
        result = node.run(**run_args)
        print(f"Result: {result}")
    except ValueError as e:
        logging.error(f"Argument validation failed: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Failed to run node: {e}")
        sys.exit(1)