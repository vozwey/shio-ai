from __future__ import annotations

import inspect
import json
import logging
import types
from dataclasses import dataclass, field
from typing import (
    Annotated,
    Any,
    Callable,
    Dict,
    List,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

logger = logging.getLogger(__name__)

_SIMPLE = {str: "string", int: "integer", float: "number", bool: "boolean"}


@dataclass
class ToolDef:
    name: str
    description: str
    fn: Callable[..., Any]
    schema: dict[str, Any] = field(default_factory=dict)


TOOLS_REGISTRY: dict[str, ToolDef] = {}


def _resolve_type(hint: Any) -> tuple[Any, str | None]:
    desc: str | None = None
    origin = get_origin(hint)

    if origin is Annotated:
        args = get_args(hint)
        desc = next((a for a in args[1:] if isinstance(a, str)), None)
        base, _ = _resolve_type(args[0])
        return base, desc

    if origin is None:
        if hint is type(None):
            return "null", desc
        return _SIMPLE.get(hint, "string"), desc

    if origin in (list, List):
        item, _ = _resolve_type(get_args(hint)[0])
        return {"type": "array", "items": {"type": item}}, desc

    if origin in (dict, Dict):
        return {"type": "object"}, desc

    if origin is Union or origin is types.UnionType:
        args = [a for a in get_args(hint) if a is not type(None)]
        if len(args) == 1:
            return _resolve_type(args[0])
        return {"oneOf": [_resolve_type(a)[0] for a in args]}, desc

    return {"type": "string"}, desc


def tool(description: str | None = None):

    def decorator(fn: Callable) -> Callable:
        name = fn.__name__
        doc = (fn.__doc__ or "").strip()
        desc = (description or doc.splitlines()[0]).strip() if doc else (description or "")
        sig = inspect.signature(fn)
        hints = get_type_hints(fn)

        properties: dict[str, Any] = {}
        required: list[str] = []

        for param_name, param in sig.parameters.items():
            if param_name == "user_id":
                continue
            hint = hints.get(param_name, str)
            json_def, param_desc = _resolve_type(hint)
            prop: dict[str, Any] = {"type": json_def} if isinstance(json_def, str) else json_def
            if param_desc:
                prop["description"] = param_desc
            properties[param_name] = prop
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        TOOLS_REGISTRY[name] = ToolDef(
            name=name,
            description=desc,
            fn=fn,
            schema={"type": "object", "properties": properties, "required": required},
        )
        return fn

    return decorator


def get_tools_schema() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.schema,
            },
        }
        for t in TOOLS_REGISTRY.values()
    ]


def generate_tools_json(indent: int = 1) -> str:
    return json.dumps(get_tools_schema(), ensure_ascii=False, indent=indent)


async def execute_tool(user_id: int, name: str, args: str) -> str:
    params = json.loads(args)
    tool_def = TOOLS_REGISTRY.get(name)
    if tool_def is None:
        return "Неизвестный инструмент."
    try:
        result = tool_def.fn(**params)
        if inspect.isawaitable(result):
            result = await result
        return str(result)
    except Exception as e:
        logger.exception("Ошибка при выполнении тула %s", name)
        return f"Ошибка тула: {e}"


def inject_tools_prompt(system_prompt: str) -> str:
    if not TOOLS_REGISTRY:
        return system_prompt
    names = ", ".join(t.name for t in TOOLS_REGISTRY.values())
    block = (
        "\n\n## Доступные инструменты\n"
        f"У тебя есть инструменты: {names}. Используй их эффективно и по делу.\n"
        "Схемы инструментов (OpenAI function calling, JSON):\n"
        f"```json\n{generate_tools_json()}\n```\n"
    )
    return system_prompt + block
