from node_framework import NodeFramework

framework = NodeFramework(nodes_dir="action_nodes", config_file="config.yaml")

result = framework.chain(
    "emailgetter",
    "dbwriter",
    emailgetter={"max_emails": 2},
    dbwriter={"table_name": "emails"}
)

print(result)
