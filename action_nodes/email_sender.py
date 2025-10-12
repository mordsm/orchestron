import smtplib
from email.mime.text import MIMEText
from base_node import ActionNode
import os
import argparse

class EmailSenderNode(ActionNode):
    """Node to send an email. Config: {'smtp_server', 'port', 'user', 'password'}."""
    
    @classmethod
    def get_parameters(cls):
        return {
            "parameters": [
                {"name": "to_email", "type": "string", "description": "Recipient email address"},
                {"name": "subject", "type": "string", "description": "Email subject"},
                {"name": "body", "type": "string", "description": "Email body"}
            ],
            "required": ["to_email", "subject", "body"]
        }
    
    def run(self, to_email, subject, body):
        self.validate(to_email=to_email, subject=subject, body=body)
        server = self.config.get('smtp_server', os.getenv('SMTP_SERVER', 'smtp.gmail.com'))
        port = self.config.get('port', int(os.getenv('SMTP_PORT', 587)))
        user = self.config.get('user', os.getenv('SMTP_USER'))
        password = self.config.get('password', os.getenv('SMTP_PASSWORD'))
        
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = user
        msg['To'] = to_email
        
        with smtplib.SMTP(server, port) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(msg)
        
        self.logger.info(f"Email sent to {to_email}")
        return {"status": "sent"}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send email standalone.")
    for param in EmailSenderNode.get_parameters()["parameters"]:
        parser.add_argument(f"--{param['name']}", 
                          required=param["name"] in EmailSenderNode.get_parameters()["required"],
                          help=param["description"])
    
    args = parser.parse_args()
    node = EmailSenderNode()
    node.run(**vars(args))