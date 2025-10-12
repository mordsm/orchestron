from abc import ABC, abstractmethod
import logging
from typing import Dict, Any, Optional

class ActionNode(ABC):
    """Base class for action nodes with parameter schema support."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        logging.basicConfig(level=logging.INFO)
    
    @abstractmethod
    def run(self, *args, **kwargs):
        """Execute the node's action. Args/kwargs must match get_parameters() schema."""
        pass
    
    @classmethod
    def get_parameters(cls) -> Dict[str, Any]:
        """Return parameter schema (JSON Schema-like dict). Override in subclasses."""
        return {
            "parameters": [],
            "required": []
        }
    
    def validate(self, **kwargs):
        """Validate input parameters against schema."""
        schema = self.get_parameters()
        required = set(schema.get("required", []))
        provided = set(kwargs.keys())
        
        # Check missing required parameters
        missing = required - provided
        if missing:
            raise ValueError(f"Missing required parameters: {missing}")
        
        # Basic type checking (extend as needed)
        for param in schema.get("parameters", []):
            name = param["name"]
            if name in kwargs:
                expected_type = param.get("type")
                actual = kwargs[name]
                if expected_type == "string" and not isinstance(actual, str):
                    raise TypeError(f"Parameter '{name}' must be a string")
                elif expected_type == "integer" and not isinstance(actual, int):
                    raise TypeError(f"Parameter '{name}' must be an integer")
    
    def __call__(self, *args, **kwargs):
        """Make node callable. Validates inputs before running."""
        self.validate(**kwargs)
        return self.run(*args, **kwargs)