# example_usage.py
from node_framework import NodeFramework

# Initialize framework
framework = NodeFramework(nodes_dir='action_nodes', config_file='config.yaml')

# Get tool schema (e.g., for AI agent)
email_schema = framework.get_tool_schema('emailsender')
print(email_schema)
# Output:
# {
#     'name': 'emailsender',
#     'description': 'Node to send an email...',
#     'parameters': {
#         'parameters': [
#             {'name': 'to_email', 'type': 'string', 'description': 'Recipient email address'},
#             {'name': 'subject', 'type': 'string', 'description': 'Email subject'},
#             {'name': 'body', 'type': 'string', 'description': 'Email body'}
#         ],
#         'required': ['to_email', 'subject', 'body']
#     }
# }

# List all tools
print(framework.list_tools())

# Call as a tool
tool = framework.get_tool('emailsender')
result = tool.run(to_email="test@domain.com", subject="Hi", body="Hello")
print(result)  # {'status': 'sent'}

# Chain tools
sequence = [
    ('emailgetter', [], {'max_emails': 2}),
    ('dbwriter', ['emails'], {'data_dict': {'from': 'test@domain.com', 'subject': 'Hi'}})
]
results = framework.chain_nodes(sequence)