# tools/langchain_adapter.py
from typing import Type, Optional, get_type_hints
from pydantic import BaseModel, Field, create_model
from langchain_core.tools import StructuredTool

from tools.dispatch import TOOL_DISPATCH
from tools.schemas import TOOLS

def _create_args_schema_from_openai(tool_def: dict) -> Type[BaseModel]:
    """
    Dynamically create a Pydantic model from OpenAI tool parameters using create_model.
    """
    params = tool_def["function"]["parameters"]
    properties = params.get("properties", {})
    required = params.get("required", [])

    field_definitions = {}
    for name, prop in properties.items():
        field_type = str
        if prop.get("type") == "integer":
            field_type = int
        elif prop.get("type") == "number":
            field_type = float
        elif prop.get("type") == "array":
            field_type = list
        elif prop.get("type") == "object":
            field_type = dict
        elif prop.get("type") == "boolean":
            field_type = bool

        # Use ... for required fields, None for optional
        default = ... if name in required else None
        field_definitions[name] = (field_type, Field(default, description=prop.get("description", "")))

    # create_model handles the type annotations correctly
    return create_model(
        f"{tool_def['function']['name']}_args",
        **field_definitions
    )

# Build LangChain tools
LANGCHAIN_TOOLS = []
for tool_def in TOOLS:
    func_name = tool_def["function"]["name"]
    if func_name not in TOOL_DISPATCH:
        continue

    func = TOOL_DISPATCH[func_name]
    description = tool_def["function"]["description"]
    args_schema = _create_args_schema_from_openai(tool_def)

    structured_tool = StructuredTool(
        name=func_name,
        description=description,
        func=func,
        args_schema=args_schema,
    )
    LANGCHAIN_TOOLS.append(structured_tool)

def get_tools():
    return LANGCHAIN_TOOLS