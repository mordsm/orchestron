from langchain.tools import BaseTool

class LangChainToolAdapter(BaseTool):
    name: str
    description: str
    action_node: ActionNode
    
    def _run(self, **kwargs):
        return self.action_node(**kwargs)
    
    def _arun(self, **kwargs):
        raise NotImplementedError("Async not supported yet")
    
    @property
    def args_schema(self):
        schema = self.action_node.get_parameters()
        # Convert to LangChain schema if needed
        return type(f"{self.name}Schema", (), {
            "properties": {p["name"]: {"type": p["type"], "description": p["description"]} for p in schema["parameters"]},
            "required": schema["required"]
        })

# Wrap in framework
def as_langchain_tool(self, name):
    tool = self.get_tool(name)
    return LangChainToolAdapter(
        name=tool.name,
        description=tool.description,
        action_node=tool.node
    )

# Add to NodeFramework
NodeFramework.as_langchain_tool = as_langchain_tool

# Usage
lc_tool = framework.as_langchain_tool('emailsender')
lc_tool.invoke({"to_email": "test@domain.com", "subject": "Hi", "body": "Hello"})
