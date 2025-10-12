import importlib.util
import os
import yaml
import argparse
import sys
import logging
from pathlib import Path
from base_node import ActionNode
from typing import Dict, Any, Optional
from dataclasses import dataclass
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


@dataclass
class ToolNode:
    """Wrapper to make ActionNode compatible with tool-calling frameworks."""
    node: ActionNode
    name: str
    description: str
    parameters: Dict[str, Any]
    
    def run(self, **kwargs):
        return self.node(**kwargs)
    
    def get_schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }

class NodeFramework:
    """Framework to manage nodes with parameter discovery and tool support."""
    
    def __init__(self, nodes_dir='.', config_file=None):
        self.logger = logging.getLogger(__name__)
        self.nodes = {}  # {name: node_class}
        self.tools = {}  # {name: ToolNode}
        self.config = self._load_config(config_file)
        self._discover_nodes(nodes_dir)
        
    
    def _load_config(self, config_file):
        if config_file and Path(config_file).exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
                self.logger.info(f"Loaded config from {config_file}")
                return config
            except yaml.YAMLError as e:
                self.logger.error(f"Failed to load config file {config_file}: {e}")
                return {}
        self.logger.warning(f"No config file provided or {config_file} not found")
        return {}
    
    def _discover_nodes(self, nodes_dir):
        nodes_dir = Path(nodes_dir).resolve()
        self.logger.info(f"Scanning directory {nodes_dir} for nodes")
        if not nodes_dir.exists():
            self.logger.error(f"Directory {nodes_dir} does not exist")
            return
        
        found_files = list(nodes_dir.glob('*.py'))
        if not found_files:
            self.logger.warning(f"No .py files found in {nodes_dir}")
        
        for file in found_files:
            if file.stem in ['base_node', 'node_framework']:
                self.logger.debug(f"Skipping file {file}")
                continue
            self.logger.debug(f"Processing file {file}")
            try:
                spec = importlib.util.spec_from_file_location(file.stem, file)
                if spec is None:
                    self.logger.error(f"Failed to create spec for {file}")
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[file.stem] = module
                spec.loader.exec_module(module)
                found_node = False
                for attr in dir(module):
                    cls = getattr(module, attr)
                    if isinstance(cls, type) and issubclass(cls, ActionNode) and cls != ActionNode:
                        name = cls.__name__.replace('Node', '').lower()
                        self.nodes[name] = cls
                        parameters = cls.get_parameters()
                        description = cls.__doc__.strip() if cls.__doc__ else f"{name} action node"
                        self.tools[name] = ToolNode(
                            node=cls(self.config.get(name, {})),
                            name=name,
                            description=description,
                            parameters=parameters
                        )
                        self.logger.info(f"Registered node and tool: {name} from {file}")
                        found_node = True
                if not found_node:
                    self.logger.warning(f"No valid ActionNode subclasses found in {file}")
            except Exception as e:
                self.logger.error(f"Failed to load node from {file}: {e}")
        
    def get_node(self, name, config=None):
        cls = self.nodes.get(name)
        if not cls:
            raise ValueError(f"Node '{name}' not found")
        node_config = self.config.get(name, {})
        node_config.update(config or {})
        return cls(node_config)
    
    def call_node(self, name, *args, **kwargs):
        self.logger.info(f"Calling node {name} with args={args}, kwargs={kwargs}")
        node = self.get_node(name)
        return node(*args, **kwargs)
    
    def get_tool(self, name):
        tool = self.tools.get(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found")
        return tool
    
    def get_tool_schema(self, name):
        tool = self.get_tool(name)
        return tool.get_schema()
    
    def list_tools(self):
        return [
            {
                "name": name,
                "description": tool.description,
                "parameters": tool.parameters
            }
            for name, tool in self.tools.items()
        ]
    
    def chain(self, *node_names, **kwargs):
        """
        Dynamically chain nodes — output from one node becomes input to the next.
        Example:
            framework.chain(
                "emailgetter", "dbwriter",
                emailgetter={"max_emails": 3},
                dbwriter={"table_name": "emails"}
            )
        """
        result = None
        for name in node_names:
            if name not in self.nodes:
                raise ValueError(f"Node '{name}' not found. Available: {list(self.nodes.keys())}")

            node = self.get_node(name)
            params = kwargs.get(name, {}).copy()

            # If previous node returned something, pass it as 'data' if not already provided
            if result is not None:
                sig = node.get_parameters()
                param_names = [p["name"] for p in sig.get("parameters", [])]
                if "data" in param_names and "data" not in params:
                    params["data"] = result

            self.logger.info(f"Running node '{name}' with params: {params}")
            result = node.run(**params)
            self.logger.info(f"Output from '{name}': {result}")

        return result


    def chain_nodes(self, sequence):
        results = []
        for name, args, kwargs in sequence:
            result = self.call_node(name, *args, **kwargs)
            results.append(result)
        return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Orchestron: Run modular action nodes.",
        epilog="""
Examples:
  python node_framework.py --config config.yaml list
  python node_framework.py --config config.yaml run emailsender --to_email test@domain.com --subject "Test" --body "Hello"
  python node_framework.py --config config.yaml run emailgetter --max_emails 3
  python node_framework.py --config config.yaml chain emailgetter_to_db --max_emails 3
  python node_framework.py --config config.yaml chain youtubetranscript_to_db --youtube_url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --language "en" --summary_sentences 3
  python node_framework.py --config config.yaml chain eventcreator_to_db --title "Team Meeting" --start_time "2025-09-28T10:00:00+03:00" --end_time "2025-09-28T11:00:00+03:00" --description "Weekly team sync" --calendar_id "primary"
"""
    )
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config YAML file")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List available nodes")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run a specific node")
    run_parser.add_argument("node_name", help="Name of the node to run (e.g., emailsender, emailgetter, eventcreator)")

    # Chain command
    chain_parser = subparsers.add_parser("chain", help="Run a chain of nodes")
    chain_parser.add_argument("chain_name", choices=["emailgetter_to_db", "youtubetranscript_to_db", "eventcreator_to_db"], help="Name of the node chain")
    chain_parser.add_argument("--max_emails", type=int, default=5, help="Maximum emails to fetch (for emailgetter_to_db)")
    chain_parser.add_argument("--youtube_url", type=str, help="YouTube video URL (for youtubetranscript_to_db)")
    chain_parser.add_argument("--language", type=str, default="en", help="Transcript language code (for youtubetranscript_to_db)")
    chain_parser.add_argument("--prompt", type=str, default="Extract the main keypoints and important topics discussed in this video", help="Prompt for OpenAI analysis")
    chain_parser.add_argument("--max_length", type=int, default=500, help="Max length of analysis output")
    chain_parser.add_argument("--include_metadata", type=bool, default=True, help="Include video metadata")
    chain_parser.add_argument("--use_transcript", type=bool, default=True, help="Use transcript if available")
    chain_parser.add_argument("--title", type=str, help="Event title (for eventcreator_to_db)")
    chain_parser.add_argument("--start_time", type=str, help="Event start time (ISO format, for eventcreator_to_db)")
    chain_parser.add_argument("--end_time", type=str, help="Event end time (ISO format, for eventcreator_to_db)")
    chain_parser.add_argument("--description", type=str, default="", help="Event description (for eventcreator_to_db)")
    chain_parser.add_argument("--calendar_id", type=str, default="primary", help="Google Calendar ID (for eventcreator_to_db)")

    args, unknown_args = parser.parse_known_args()
    self.logger.info(f"sys.argv: {sys.argv}")
    self.logger.info(f"Parsed args: {vars(args)}, Unknown args: {unknown_args}")
    # orchestron/api.py
    from .node_framework import NodeFramework

    _framework = NodeFramework(nodes_dir="action_nodes", config_file="config.yaml")

    def get_tool(name):
        """Return a callable node as a tool (LangChain-style)."""
        tool = _framework.get_tool(name)
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "function": tool.node.run
        }

    def list_tools():
        """Return list of available tool schemas."""
        return _framework.list_tools()

    def chain(self, *node_names, **kwargs):
        """
        Dynamically chain nodes — output from one node becomes input to the next.
        Example:
            framework.chain(
                "emailgetter", "dbwriter",
                emailgetter={"max_emails": 3},
                dbwriter={"table_name": "emails"}
            )
        """
        result = None
        for name in node_names:
            node = self.get_node(name)
            params = kwargs.get(name, {})
            if result is not None:
                # Try to pass the previous result if next node expects 'data'
                if "data" in node.get_parameters().get("required", []):
                    params["data"] = result
            result = node.run(**params)
        return result

    if not args.command:
        self.logger.error("No command provided. Use 'list', 'run', or 'chain'.")
        parser.print_help()
        sys.exit(1)

    # Initialize framework
    framework = NodeFramework(nodes_dir="action_nodes", config_file=args.config)

    if args.command == "list":
        tools = framework.list_tools()
        if not tools:
            print("No nodes registered. Check 'action_nodes' directory and logs for errors.")
            sys.exit(1)
        print("Available Nodes:")
        for tool in tools:
            print(f"\nName: {tool['name']}")
            print(f"Description: {tool['description']}")
            print("Parameters:")
            for param in tool['parameters']['parameters']:
                required = " (required)" if param['name'] in tool['parameters']['required'] else f" (default: {param.get('default', 'None')})"
                print(f"  --{param['name']}: {param['description']}{required}")
        sys.exit(0)

    if args.command == "run":
        if args.node_name not in framework.nodes:
            self.logger.error(f"Node '{args.node_name}' not found. Use 'list' to see available nodes.")
            sys.exit(1)
        
        # Get node schema
        schema = framework.get_tool_schema(args.node_name)
        parameters = schema["parameters"]["parameters"]
        required = schema["parameters"]["required"]

        # Create new parser for node-specific arguments
        node_parser = argparse.ArgumentParser(description=f"Run {args.node_name}")
        for param in parameters:
            arg_type = int if param["type"] == "integer" else bool if param["type"] == "boolean" else str
            default = param.get("default")
            node_parser.add_argument(
                f"--{param['name']}",
                type=arg_type,
                required=param["name"] in required and default is None,
                default=default,
                help=param["description"]
            )

        # Parse remaining arguments with strict validation
        try:
            node_args = node_parser.parse_args(unknown_args)
        except SystemExit:
            self.logger.error(f"Invalid arguments for node '{args.node_name}'. Required parameters: {required}")
            node_parser.print_help()
            sys.exit(1)

        kwargs = {k: v for k, v in vars(node_args).items() if v is not None}

        # Debug mode defaults
        is_debug = hasattr(sys, 'gettrace') and sys.gettrace() is not None
        if is_debug and not kwargs and args.node_name == "emailsender":
            kwargs = {
                "to_email": "test@domain.com",
                "subject": "Debug Test",
                "body": "Debug email body"
            }
            self.logger.warning(f"Debug mode: Using default args for {args.node_name}: {kwargs}")
        elif is_debug and not kwargs and args.node_name == "emailgetter":
            kwargs = {"max_emails": 3}
            self.logger.warning(f"Debug mode: Using default args for {args.node_name}: {kwargs}")
        elif is_debug and not kwargs and args.node_name == "youtubetranscript":
            kwargs = {
                "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "language": "en",
                "summary_sentences": 3
            }
            self.logger.warning(f"Debug mode: Using default args for {args.node_name}: {kwargs}")
        elif is_debug and not kwargs and args.node_name == "eventcreator":
            kwargs = {
                "title": "Test Event",
                "start_time": "2025-09-29T10:00:00+03:00",
                "end_time": "2025-09-29T11:00:00+03:00",
                "description": "Debug event description",
                "calendar_id": "primary"
            }
            self.logger.warning(f"Debug mode: Using default args for {args.node_name}: {kwargs}")

        # Validate required parameters
        missing = [param for param in required if param not in kwargs]
        if missing:
            self.logger.error(f"Missing required parameters for {args.node_name}: {missing}")
            node_parser.print_help()
            sys.exit(1)

        # Run the node
        try:
            result = framework.call_node(args.node_name, **kwargs)
            print(f"Result: {json.dumps(result, indent=2, ensure_ascii=False)}")
        except Exception as e:
            self.logger.error(f"Failed to run node {args.node_name}: {e}")
            sys.exit(1)

    if args.command == "chain":
        if args.chain_name == "emailgetter_to_db":
            try:
                emails = framework.call_node("emailgetter", max_emails=args.max_emails)
                result = framework.call_node("dbwriter", data=emails, data_type="email")
                print(f"Result: {json.dumps(result, indent=2, ensure_ascii=False)}")
            except Exception as e:
                self.logger.error(f"Failed to run chain '{args.chain_name}': {e}")
                sys.exit(1)
        elif args.chain_name == "youtubetranscript_to_db":
            try:
                transcript_data = framework.call_node(
                    "youtubeanalyzer",
                    url=args.youtube_url,
                    language=args.language,
                    prompt=args.prompt,
                    max_length=args.max_length,
                    include_metadata=args.include_metadata,
                    use_transcript=args.use_transcript
                )
                transcript_data['video_url'] = args.youtube_url
                result = framework.call_node("dbwriter", data=transcript_data, data_type="transcript")
                print(f"Result: {json.dumps(result, indent=2, ensure_ascii=False)}")
            except Exception as e:
                self.logger.error(f"Failed to run chain '{args.chain_name}': {e}")
                sys.exit(1)
        elif args.chain_name == "eventcreator_to_db":
            try:
                event_data = framework.call_node(
                    "eventcreator",
                    title=args.title,
                    start_time=args.start_time,
                    end_time=args.end_time,
                    description=args.description,
                    calendar_id=args.calendar_id
                )
                # Include event_id in data for DBWriterNode
                event_data_for_db = event_data['event_details'].copy()
                event_data_for_db['event_id'] = event_data['event_id']
                result = framework.call_node("dbwriter", data=event_data_for_db, data_type="event")
                print(f"Result: {json.dumps(result, indent=2, ensure_ascii=False)}")
            except Exception as e:
                self.logger.error(f"Failed to run chain '{args.chain_name}': {e}")
                sys.exit(1)
        else:
            self.logger.error(f"Unknown chain '{args.chain_name}'. Supported: emailgetter_to_db, youtubetranscript_to_db, eventcreator_to_db")
            parser.print_help()
            sys.exit(1)