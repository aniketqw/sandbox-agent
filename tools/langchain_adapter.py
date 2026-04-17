# tools/langchain_adapter.py
from typing import Type, Dict, Any
from pydantic import BaseModel, Field, create_model
from langchain_core.tools import StructuredTool

from tools.dispatch import TOOL_DISPATCH
from tools.schemas import TOOLS


def _create_args_schema_from_openai(tool_def: dict) -> Type[BaseModel]:
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

        default = ... if name in required else None
        field_definitions[name] = (field_type, Field(default, description=prop.get("description", "")))

    return create_model(f"{tool_def['function']['name']}_args", **field_definitions)


def _clean_schema_for_anthropic(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively remove 'title' fields and 'default' keys with null values.
    Also ensures 'required' lists only fields that are actually required.
    """
    # Remove Pydantic metadata
    schema.pop("title", None)
    schema.pop("description", None)   # top-level description not needed
    
    # Process properties
    if "properties" in schema:
        cleaned_props = {}
        for prop_name, prop_schema in schema["properties"].items():
            if isinstance(prop_schema, dict):
                prop_schema.pop("title", None)
                # Remove default: null
                if "default" in prop_schema and prop_schema["default"] is None:
                    del prop_schema["default"]
                cleaned_props[prop_name] = prop_schema
        schema["properties"] = cleaned_props

    # Clean items if array type
    if "items" in schema and isinstance(schema["items"], dict):
        schema["items"].pop("title", None)

    # Ensure required only contains properties that exist
    if "required" in schema:
        existing_props = set(schema.get("properties", {}).keys())
        schema["required"] = [r for r in schema["required"] if r in existing_props]
        if not schema["required"]:
            del schema["required"]

    # Add type if missing
    if "type" not in schema:
        schema["type"] = "object"

    return schema


def _get_tool_schema(tool: StructuredTool) -> dict:
    if tool.args_schema:
        schema = tool.args_schema.model_json_schema()
        return _clean_schema_for_anthropic(schema)
    return {"type": "object", "properties": {}}


LANGCHAIN_TOOLS = []
for tool_def in TOOLS:
    func_name = tool_def["function"]["name"]
    if func_name not in TOOL_DISPATCH:
        continue
    func = TOOL_DISPATCH[func_name]
    description = tool_def["function"]["description"]
    args_schema = _create_args_schema_from_openai(tool_def)

    tool = StructuredTool(
        name=func_name,
        description=description,
        func=func,
        args_schema=args_schema,
    )
    LANGCHAIN_TOOLS.append(tool)


def get_tools():
    return LANGCHAIN_TOOLS