"""
graph_node_framework.py

LangGraph-based agent that uses your existing action_nodes
(emailgetter, dbwriter, youtubeanalyzer, etc.) as tools.

CLI example:
    python graph_node_framework.py --config config.yaml \
        --query "get the last email content and write it to email table in db"
"""

import argparse
import importlib.util
import inspect
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv

# LangChain / LangGraph
from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
    SystemMessage,
)
from typing_extensions import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, START, END

# ---- Load env ----
load_dotenv()

# ---- Paths ----
BASE_DIR = Path(__file__).resolve().parent
ACTION_NODES_DIR = BASE_DIR / "action_nodes"

logger = logging.getLogger("graph_node_framework")


# =============================================================================
# 1. Load config.yaml
# =============================================================================

def load_config(path: str) -> Dict[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# =============================================================================
# 2. Load action_nodes dynamically (similar to node_framework)
# =============================================================================

class ActionNodeRegistry:
    """
    Registry for ActionNode-based nodes discovered in action_nodes/.

    Assumes each node file defines subclasses of base_node.ActionNode
    that expose a `.run(**kwargs)` method.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.nodes: Dict[str, Any] = {}

    def scan_and_register(self):
        logger.info(f"Scanning directory {ACTION_NODES_DIR} for nodes")
        for py_file in ACTION_NODES_DIR.glob("*.py"):
            if py_file.name.startswith("_"):
                continue  # skip disabled files
            self._load_module_nodes(py_file)

    def _load_module_nodes(self, path: Path):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            logger.warning(f"Could not load module from {path}")
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore

        # Lazy import base class name
        ActionNode = None
        if hasattr(module, "ActionNode"):
            ActionNode = module.ActionNode
        else:
            # try import from base_node
            try:
                from base_node import ActionNode as BaseActionNode  # type: ignore
                ActionNode = BaseActionNode
            except Exception:
                pass

        for name, obj in inspect.getmembers(module, inspect.isclass):
            if ActionNode and issubclass(obj, ActionNode) and obj is not ActionNode:
                node_name = getattr(obj, "tool_name", None) or name.lower()
                # Per-node config section (e.g. config["dbwriter"])
                node_cfg = self.config.get(node_name, {})
                try:
                    instance = obj(config=node_cfg)
                    self.nodes[node_name] = instance
                    logger.info(
                        f"Registered node: {node_name} from {path}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to init node {name} from {path}: {e}",
                        exc_info=True,
                    )

    def get(self, name: str):
        if name not in self.nodes:
            raise KeyError(f"Node '{name}' not found in registry")
        return self.nodes[name]


# =============================================================================
# 3. Define Tools that wrap specific nodes
# =============================================================================

class NodeToolContext:
    """Holds registry + global config, injected into tool implementations."""

    def __init__(self, registry: ActionNodeRegistry, config: Dict[str, Any]):
        self.registry = registry
        self.config = config


def build_tools(ctx: NodeToolContext):
    """
    Build a list of LangChain tools (for LangGraph agent) around your key nodes.

    You can extend this with more node wrappers as needed.
    """

    registry = ctx.registry

    # ---- 3.1 wrap emailgetter: get last email ----

    @tool
    def get_last_email(max_emails: int = 1) -> str:
        """
        Get the latest email(s) content using the 'emailgetter' node.
        Returns JSON with a list of emails.
        """
        node = registry.get("emailgetter")
        # NOTE: adapt param names to your actual node signature if needed
        result = node.run(max_emails=max_emails)
        # Expect result to be serializable; if not, adapt here
        return json.dumps(result, ensure_ascii=False)

    # ---- 3.2 wrap dbwriter: write arbitrary data to a table ----

    @tool
    def write_to_db(
        payload_json: str,
        data_type: str = "generic",
        table_name: str = "emails",
    ) -> str:
        """
        Write a JSON payload into DB using 'dbwriter' node.

        Args:
            payload_json: JSON string representing the data to insert.
            data_type: Logical type (e.g. 'email', 'transcript').
            table_name: Target DB table name.
        """
        node = registry.get("dbwriter")
        try:
            data = json.loads(payload_json)
        except json.JSONDecodeError:
            raise ValueError("payload_json must be valid JSON string")

        # Many DBWriterNode implementations expect: data, data_type, table_name
        result = node.run(data=data, data_type=data_type, table_name=table_name)
        return json.dumps(result, ensure_ascii=False)

    # ---- 3.3 generic node runner: run any node by name with JSON params ----

    @tool
    def run_node(node_name: str, params_json: str) -> str:
        """
        Run an arbitrary ActionNode by its name and a JSON-encoded params dict.

        Example:
            run_node(
                node_name="dbwriter",
                params_json='{"data": {"x":1}, "data_type": "test", "table_name": "debug"}'
            )
        """
        node = registry.get(node_name)
        try:
            params = json.loads(params_json)
        except json.JSONDecodeError:
            raise ValueError("params_json must be valid JSON dict string")

        if not isinstance(params, dict):
            raise ValueError("params_json must decode to a dict")

        result = node.run(**params)
        return json.dumps(result, ensure_ascii=False)

    # You can add more specialized tools if you want
    # e.g., a youtube summary tool that calls youtubeanalyzer, etc.

    return [get_last_email, write_to_db, run_node]


# =============================================================================
# 4. Define LangGraph state and nodes (LLM + tool executor)
# =============================================================================

class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], operator.add]


def build_agent(tools, system_prompt: str) -> Any:
    """
    Build a LangGraph agent that:
    - Uses a chat model with tools
    - Loops: LLM → tools → LLM ... until no tool calls
    """

    # 4.1 Chat model with tools bound
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        temperature=0,
    )
    tools_by_name = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)

    # 4.2 LLM node
    def llm_call(state: AgentState) -> Dict[str, Any]:
        messages = state["messages"]
        resp = llm_with_tools.invoke(
            [SystemMessage(content=system_prompt)] + messages
        )
        return {"messages": [resp]}

    # 4.3 Tool executor node
    def tool_node(state: AgentState) -> Dict[str, Any]:
        last = state["messages"][-1]
        results: List[ToolMessage] = []
        for tool_call in last.tool_calls:
            tool_name = tool_call["name"]
            args = tool_call["args"]
            tool = tools_by_name[tool_name]
            observation = tool.invoke(args)
            results.append(
                ToolMessage(
                    content=observation,
                    tool_call_id=tool_call["id"],
                )
            )
        return {"messages": results}

    # 4.4 Routing logic (continue or stop)
    from typing import Literal

    def should_continue(state: AgentState) -> Literal["tool_node", END]:
        messages = state["messages"]
        last_msg = messages[-1]
        if getattr(last_msg, "tool_calls", None):
            return "tool_node"
        return END

    # 4.5 Build graph
    graph = StateGraph(AgentState)
    graph.add_node("llm_call", llm_call)
    graph.add_node("tool_node", tool_node)

    graph.add_edge(START, "llm_call")
    graph.add_conditional_edges("llm_call", should_continue, ["tool_node", END])
    graph.add_edge("tool_node", "llm_call")

    agent = graph.compile()
    return agent


# =============================================================================
# 5. CLI entry: run a natural-language query
# =============================================================================

def run_query(config_path: str, query: str):
    # Load config
    config = load_config(config_path)

    # Build registry
    registry = ActionNodeRegistry(config=config)
    registry.scan_and_register()

    # Build tools from registry
    ctx = NodeToolContext(registry=registry, config=config)
    tools = build_tools(ctx)

    # System prompt: explain how the agent should behave
    system_prompt = (
        "You are an orchestration agent over existing tools (emailgetter, dbwriter, etc.). "
        "The user will describe high-level goals in natural language, like: "
        "'get the last email content and write it to email table in db'. "
        "You must:\n"
        "1. Decide which tools to call and in what order.\n"
        "2. Use get_last_email to retrieve recent emails.\n"
        "3. Use write_to_db to store data in the database, with a sensible table_name.\n"
        "4. You may call run_node for advanced usage if needed.\n"
        "5. Never ask the user for JSON; decide the structure yourself.\n"
        "6. At the end, summarize what you did and the result."
    )

    agent = build_agent(tools, system_prompt=system_prompt)

    # Initial state: just the human query
    state: AgentState = {
        "messages": [HumanMessage(content=query)]
    }

    result_state = agent.invoke(state)
    final_messages = result_state["messages"]

    # Print final conversation
    print("=== Agent run complete ===")
    for m in final_messages:
        role = m.__class__.__name__
        print(f"[{role}] {m.content}")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="LangGraph-based orchestration over action_nodes."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to config YAML file",
    )
    parser.add_argument(
        "--query",
        type=str,
        required=True,
        help="Natural language instruction for the agent",
    )
    args = parser.parse_args()

    run_query(config_path=args.config, query=args.query)


if __name__ == "__main__":
    main()
