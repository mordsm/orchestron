from node_framework import NodeFramework
import logging

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    framework = NodeFramework(nodes_dir="action_nodes", config_file="config.yaml")
    
    # Fetch emails
    emails = framework.call_node("emailgetter", max_emails=3)
    
    # Write to database
    result = framework.call_node("dbwriter", emails=emails)
    
    print(f"Result: {result}")