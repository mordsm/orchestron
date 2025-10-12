import imaplib
import email
from email.header import decode_header
from base_node import ActionNode
import os
import argparse
import yaml
from pathlib import Path
import sys
import logging
from typing import List, Dict

class EmailGetterNode(ActionNode):
    """Node to fetch recent emails. Config: {'imap_server', 'user', 'password'}."""
    
    @classmethod
    def get_parameters(cls):
        return {
            "parameters": [
                {"name": "max_emails", "type": "integer", "description": "Maximum emails to fetch", "default": 5}
            ],
            "required": []
        }
    
    def validate(self, **kwargs):
        super().validate(**kwargs)
        required_config = {'imap_server', 'user', 'password'}
        missing = required_config - set(self.config.keys())
        if missing:
            env_vars = {
                'imap_server': os.getenv('IMAP_SERVER'),
                'user': os.getenv('IMAP_USER'),
                'password': os.getenv('IMAP_PASSWORD')
            }
            for key in missing:
                if env_vars[key] is None or env_vars[key].strip() == '':
                    raise ValueError(f"Missing or empty required config: {key}. Set in config.yaml or environment variable.")
                self.config[key] = env_vars[key]
        for key, value in kwargs.items():
            if key == 'max_emails' and value is not None and value <= 0:
                raise ValueError("max_emails must be positive")
    
    def run(self, max_emails: int = 5) -> List[Dict]:
        self.validate(max_emails=max_emails)
        server = self.config['imap_server']
        user = self.config['user']
        password = self.config['password']
        
        try:
            with imaplib.IMAP4_SSL(server) as imap:
                imap.login(user, password)
                imap.select("INBOX")
                _, message_numbers = imap.search(None, "ALL")
                emails = []
                for num in message_numbers[0].split()[-max_emails:]:
                    _, msg_data = imap.fetch(num, "(RFC822)")
                    email_body = msg_data[0][1]
                    msg = email.message_from_bytes(email_body)
                    
                    # Decode subject
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8")
                    
                    # Get sender
                    from_ = msg.get("From")
                    
                    # Get body (simplified, text/plain only)
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode()
                                break
                    else:
                        body = msg.get_payload(decode=True).decode()
                    
                    emails.append({
                        "from": from_,
                        "subject": subject,
                        "body": body
                    })
                
                imap.logout()
                self.logger.info(f"Fetched {len(emails)} emails")
                return emails
        except Exception as e:
            self.logger.error(f"Failed to fetch emails: {e}")
            raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch emails standalone.")
    parser.add_argument('--config', type=str, help="Path to config YAML file")
    for param in EmailGetterNode.get_parameters()["parameters"]:
        parser.add_argument(
            f"--{param['name']}",
            type=int if param["type"] == "integer" else str,
            default=param.get("default"),
            help=param["description"]
        )
    
    is_debug = hasattr(sys, 'gettrace') and sys.gettrace() is not None
    if is_debug and len(sys.argv) == 1:
        default_args = ['--max_emails', '3', '--config', 'config.yaml']
        sys.argv.extend(default_args)
        logging.warning("Debug mode detected with no arguments. Using default args: %s", default_args)
    
    args = parser.parse_args()
    
    config = {}
    if args.config and Path(args.config).exists():
        try:
            with open(args.config, 'r') as f:
                config = yaml.safe_load(f).get('emailgetter', {})
        except yaml.YAMLError as e:
            logging.error(f"Failed to load config.yaml: {e}")
            sys.exit(1)
    
    node = EmailGetterNode(config=config)
    
    logging.info("Parsed arguments: %s", vars(args))
    
    try:
        result = node.run(**vars(args))
        print(f"Result: {result}")
    except ValueError as e:
        logging.error(f"Argument validation failed: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Failed to run node: {e}")
        sys.exit(1)