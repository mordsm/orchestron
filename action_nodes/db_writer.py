import argparse
from base_node import ActionNode
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime , Table , MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import sqltypes
from sqlalchemy.orm import sessionmaker
import os
import yaml
from pathlib import Path
import logging
from typing import List, Dict
from datetime import datetime
import json
import sys

Base = declarative_base()

class Email(Base):
    """Database model for storing emails."""
    __tablename__ = 'emails'
    id = Column(Integer, primary_key=True)
    from_email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    received_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class Transcript(Base):
    """Database model for storing YouTube transcripts."""
    __tablename__ = 'transcripts'
    id = Column(Integer, primary_key=True)
    video_url = Column(String, nullable=False)
    transcript = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    keypoints = Column(Text, nullable=False)  # Store as JSON string
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class CalendarEvent(Base):
    """Database model for storing calendar events."""
    __tablename__ = 'calendar_events'
    id = Column(Integer, primary_key=True)
    event_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    calendar_id = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class DBWriterNode(ActionNode):
    """Node to write data to a database. Config: {'db_url'}."""
    
    """  @classmethod
    def get_parameters(cls):
        return {
            "parameters": [
                {
                    "name": "data",
                    "type": "dict",
                    "description": "Data to write (email: {'from', 'subject', 'body'}, transcript: {'transcript', 'summary', 'keypoints', 'video_url'}, or event: {'event_id', 'title', 'start_time', 'end_time', 'description', 'calendar_id'})"
                },
                {
                    "name": "data_type",
                    "type": "string",
                    "description": "Type of data ('email', 'transcript', or 'event')",
                    "default": "email"
                }
            ],
            "required": ["data", "data_type"]
        } """
    
    @classmethod
    def get_parameters(cls):
        return {
            "parameters": [
                {"name": "data", "type": "dict", "description": "Data to insert"},
                {"name": "table_name", "type": "string", "description": "Database table name"}
            ],
            "required": ["data", "table_name"]
        }



    logger = logging.getLogger(__name__)

    def validate(self, **kwargs):
        super().validate(**kwargs)
        required_config = {'db_url'}
        missing = required_config - set(self.config.keys())
        if missing:
            env_vars = {'db_url': os.getenv('DB_URL')}
            for key in missing:
                if env_vars[key] is None or env_vars[key].strip() == '':
                    raise ValueError(f"Missing or empty required config: {key}. Set in config.yaml or environment variable.")
                self.config[key] = env_vars[key]
        
        data = kwargs.get('data', {})
        data_type = kwargs.get('data_type', 'email')
        if not isinstance(data, (dict, list)):
            raise ValueError("Parameter 'data' must be a dict or list")
        if data_type not in ['email', 'transcript', 'event']:
            raise ValueError("data_type must be 'email', 'transcript', or 'event'")
        
        if data_type == 'email' and isinstance(data, list):
            for email in data:
                required_keys = {'from', 'subject', 'body'}
                if not isinstance(email, dict) or not required_keys.issubset(email.keys()):
                    raise ValueError(f"Each email must be a dict with keys: {required_keys}")
        elif data_type == 'email' and isinstance(data, dict):
            required_keys = {'from', 'subject', 'body'}
            if not required_keys.issubset(data.keys()):
                raise ValueError(f"Email must be a dict with keys: {required_keys}")
        elif data_type == 'transcript' and isinstance(data, dict):
            required_keys = {'transcript', 'summary', 'keypoints', 'video_url'}
            if not required_keys.issubset(data.keys()):
                raise ValueError(f"Transcript must be a dict with keys: {required_keys}")
        elif data_type == 'event' and isinstance(data, dict):
            required_keys = {'event_id', 'title', 'start_time', 'end_time', 'calendar_id'}
            if not required_keys.issubset(data.keys()):
                raise ValueError(f"Event must be a dict with keys: {required_keys}")
    





   
    def run(self, data: Dict, table_name: str):
        # ✅ Make sure validation sees both parameters
        self.validate(data=data, table_name=table_name)

        db_url = self.config['db_url']
        engine = create_engine(db_url)
        metadata = MetaData()
        metadata.reflect(bind=engine)
    
        # Automatically create table if missing
        if table_name not in metadata.tables:
            sample = data[0] if isinstance(data, list) else data
            columns = [Column("id", Integer, primary_key=True, autoincrement=True)]
            for key in sample.keys():
                columns.append(Column(key, Text))
            table = Table(table_name, metadata, *columns)
            table.create(engine)
            self.logger.info(f"Created new table '{table_name}' with columns {list(sample.keys())}")
        else:
            table = metadata.tables[table_name]

        with engine.begin() as conn:
            if isinstance(data, list):
                conn.execute(table.insert(), data)
                count = len(data)
            else:
                conn.execute(table.insert(), [data])
                count = 1

        self.logger.info(f"Wrote {count} rows into {table_name}")
        return {"status": "success", "count": count, "table": table_name}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Write data to database standalone.")
    parser.add_argument('--config', type=str, help="Path to config YAML file")
    parser.add_argument('--data', type=str, help="JSON string of data")
    parser.add_argument('--data_type', type=str, default="email", help="Type of data ('email', 'transcript', or 'event')")
    
    args = parser.parse_args()
    
    config = {}
    if args.config and Path(args.config).exists():
        try:
            with open(args.config, 'r') as f:
                config = yaml.safe_load(f).get('dbwriter', {})
        except yaml.YAMLError as e:
            logging.error(f"Failed to load config.yaml: {e}")
            sys.exit(1)
    
    node = DBWriterNode(config=config)
    
    if args.data:
        try:
            data = json.loads(args.data)
            result = node.run(data=data, data_type=args.data_type)
            print(f"Result: {result}")
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON for data: {e}")
            sys.exit(1)
        except Exception as e:
            logging.error(f"Failed to run node: {e}")
            sys.exit(1)
    else:
        logging.error("No data provided. Use --data with a JSON string.")
        sys.exit(1)