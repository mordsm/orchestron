#!/usr/bin/env python3
"""Test script for youtube-transcript-api"""

import sys

def test_transcript_api():
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        
        # Check available methods
        methods = [m for m in dir(YouTubeTranscriptApi) if not m.startswith('_')]
        print(f"Available methods: {methods}")
        
        # Test the get_transcript method
        if hasattr(YouTubeTranscriptApi, 'get_transcript'):
            print("✓ get_transcript method exists")
            try:
                # Test with a known video that should have transcripts
                transcript = YouTubeTranscriptApi.get_transcript('dQw4w9WgXcQ')
                print(f"✓ SUCCESS: Got {len(transcript)} transcript entries")
                if transcript:
                    print(f"First entry: {transcript[0]}")
                return True
            except Exception as e:
                print(f"✗ get_transcript failed: {e}")
                # Try with a different video
                try:
                    transcript = YouTubeTranscriptApi.get_transcript('GuTcle5edjk')
                    print(f"✓ SUCCESS with different video: Got {len(transcript)} transcript entries")
                    return True
                except Exception as e2:
                    print(f"✗ get_transcript also failed with second video: {e2}")
        else:
            print("✗ get_transcript method NOT found")
            
        # Test list_transcripts method
        if hasattr(YouTubeTranscriptApi, 'list_transcripts'):
            print("✓ list_transcripts method exists")
            try:
                transcript_list = YouTubeTranscriptApi.list_transcripts('dQw4w9WgXcQ')
                print(f"✓ list_transcripts works")
                # Try to get the first available transcript
                for transcript in transcript_list:
                    data = transcript.fetch()
                    print(f"✓ Got transcript in {transcript.language_code}: {len(data)} entries")
                    return True
            except Exception as e:
                print(f"✗ list_transcripts failed: {e}")
        else:
            print("✗ list_transcripts method NOT found")
            
        return False
        
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("Testing youtube-transcript-api...")
    success = test_transcript_api()
    
    if not success:
        print("\nRecommendations:")
        print("1. Try: uv remove youtube-transcript-api")
        print("2. Then: uv add 'youtube-transcript-api==0.6.2'")
        print("3. Or use the no-transcript version of the YouTube analyzer")
    else:
        print("\n✓ Transcript API is working correctly!")