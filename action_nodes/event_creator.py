from base_node import ActionNode
import logging
import argparse
from pathlib import Path
import sys
import yaml
from typing import Dict
from datetime import datetime
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os

class EventCreatorNode(ActionNode):
    """Node to create a calendar event in Google Calendar."""
    
    @classmethod
    def get_parameters(cls):
        return {
            "parameters": [
                {"name": "title", "type": "string", "description": "Event title"},
                {"name": "start_time", "type": "string", "description": "Event start time (ISO format, e.g., 2025-09-28T10:00:00+03:00)"},
                {"name": "end_time", "type": "string", "description": "Event end time (ISO format, e.g., 2025-09-28T11:00:00+03:00)"},
                {"name": "description", "type": "string", "description": "Event description", "default": ""},
                {"name": "calendar_id", "type": "string", "description": "Google Calendar ID", "default": "primary"}
            ],
            "required": ["title", "start_time", "end_time"]
        }
    
    def validate(self, **kwargs):
        super().validate(**kwargs)
        required_config = {'client_id', 'client_secret', 'refresh_token'}
        missing = required_config - set(self.config.keys())
        if missing:
            env_vars = {
                'client_id': os.getenv('GOOGLE_CLIENT_ID'),
                'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
                'refresh_token': os.getenv('GOOGLE_REFRESH_TOKEN')
            }
            for key in missing:
                if env_vars[key] is None or env_vars[key].strip() == '':
                    raise ValueError(f"Missing or empty required config: {key}. Set in config.yaml or environment variable.")
                self.config[key] = env_vars[key]
        
        try:
            datetime.fromisoformat(kwargs.get('start_time'))
            datetime.fromisoformat(kwargs.get('end_time'))
        except ValueError:
            raise ValueError("start_time and end_time must be in ISO format (e.g., 2025-09-28T10:00:00+03:00)")
    
    def run(self, title: str, start_time: str, end_time: str, description: str = "", calendar_id: str = "primary") -> Dict:
        self.validate(title=title, start_time=start_time, end_time=end_time, description=description, calendar_id=calendar_id)
        
        try:
            # Set up Google Calendar API
            creds = Credentials(
                token=None,
                refresh_token=self.config['refresh_token'],
                client_id=self.config['client_id'],
                client_secret=self.config['client_secret'],
                token_uri='https://oauth2.googleapis.com/token',
                scopes=['https://www.googleapis.com/auth/calendar.events']
            )
            service = build('calendar', 'v3', credentials=creds, cache_discovery=False)  # Disable cache
            
            # Create event
            event = {
                'summary': title,
                'description': description,
                'start': {
                    'dateTime': start_time,
                    'timeZone': 'Asia/Jerusalem',
                },
                'end': {
                    'dateTime': end_time,
                    'timeZone': 'Asia/Jerusalem',
                },
            }
            
            event_result = service.events().insert(calendarId=calendar_id, body=event).execute()
            self.logger.info(f"Created event '{title}' with ID {event_result['id']}")
            
            return {
                "status": "success",
                "event_id": event_result['id'],
                "event_details": {
                    "title": title,
                    "start_time": start_time,
                    "end_time": end_time,
                    "description": description,
                    "calendar_id": calendar_id
                },
                "timestamp": datetime.now().isoformat()
            }
        
        except HttpError as e:
            self.logger.error(f"Failed to create event: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Create a Google Calendar event.")
    parser.add_argument('--config', type=str, help="Path to config YAML file")
    for param in EventCreatorNode.get_parameters()["parameters"]:
        parser.add_argument(
            f"--{param['name']}",
            type=int if param["type"] == "integer" else str,
            default=param.get("default"),
            required=param["name"] in EventCreatorNode.get_parameters()["required"],
            help=param["description"]
        )
    
    is_debug = hasattr(sys, 'gettrace') and sys.gettrace() is not None
    if is_debug and len(sys.argv) == 1:
        default_args = [
            '--title', 'Test Event',
            '--start_time', '2025-09-29T10:00:00+03:00',
            '--end_time', '2025-09-29T11:00:00+03:00',
            '--description', 'Debug event description',
            '--calendar_id', 'primary'
        ]
        sys.argv.extend(default_args)
        logging.warning("Debug mode detected with no arguments. Using default args: %s", default_args)
    
    args = parser.parse_args()
    
    config = {}
    if args.config and Path(args.config).exists():
        try:
            with open(args.config, 'r') as f:
                config = yaml.safe_load(f).get('eventcreator', {})
        except yaml.YAMLError as e:
            logging.error(f"Failed to load config.yaml: {e}")
            sys.exit(1)
    
    node = EventCreatorNode(config=config)
    
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