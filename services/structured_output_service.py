"""
Structured Output — enforce JSON schema on model responses.

When a caller provides a json_schema in the ChatRequest, the response is:
  1. Validated against the schema
  2. If invalid: the model is asked to fix it (one retry)
  3. If still invalid: return raw response with a validation_error field

Also adds the schema instruction to the system prompt so the model knows
what structure is expected upfront (reduces fix retries).

Supported schema features (JSON Schema subset):
  type, properties, required, items, enum, minimum, maximum, minLength

Usage (API):
  POST /v1/chat
  {
    "message": "List 3 African capitals",
    "json_schema": {
      "type": "object",
      "properties": {
        "capitals": {"type": "array", "items": {"type": "string"}}
      },
      "required": ["capitals"]
    }
  }

Response includes:
  {"type": "structured", "data": {...}, "valid": true}
  or
  {"type": "structured", "data": null, "raw": "...", "valid": false, "error": "..."}
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional


def build_schema_instruction(schema: dict) -> str:
    """
    Convert a JSON schema to a concise system prompt instruction.
    Injected before the main system prompt so the model knows the output format.
    """
    try:
        schema_str = json.dumps(schema, indent=2)
    except Exception:
        return ""

    return (
        "**Output format requirement:** Respond with ONLY valid JSON matching this schema. "
        "No prose, no markdown fences, no explanation — pure JSON only.\n"
        f"Schema:\n```json\n{schema_str}\n```"
    )


def extract_json(text: str) -> Optional[Any]:
    """Extract JSON from model response — handles markdown fences and leading prose."""
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Find first { or [ and try from there
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start == -1:
            continue
        # Find matching close bracket (simple approach)
        end = text.rfind(end_char)
        if end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue

    return None


def validate_against_schema(data: Any, schema: dict) -> tuple[bool, str]:
    """
    Validate data against a JSON Schema subset.
    Returns (valid, error_message).
    Uses jsonschema if available, falls back to manual checks.
    """
    try:
        import jsonschema
        jsonschema.validate(instance=data, schema=schema)
        return True, ""
    except ImportError:
        pass
    except Exception as e:
        return False, str(e)

    # Manual fallback for basic schemas
    return _manual_validate(data, schema)


def _manual_validate(data: Any, schema: dict, path: str = "root") -> tuple[bool, str]:
    """Basic JSON Schema validation without jsonschema library."""
    schema_type = schema.get("type")

    if schema_type == "object":
        if not isinstance(data, dict):
            return False, f"{path}: expected object, got {type(data).__name__}"
        required = schema.get("required", [])
        for field in required:
            if field not in data:
                return False, f"{path}: missing required field '{field}'"
        props = schema.get("properties", {})
        for key, subschema in props.items():
            if key in data:
                ok, err = _manual_validate(data[key], subschema, f"{path}.{key}")
                if not ok:
                    return False, err

    elif schema_type == "array":
        if not isinstance(data, list):
            return False, f"{path}: expected array, got {type(data).__name__}"
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(data):
                ok, err = _manual_validate(item, items_schema, f"{path}[{i}]")
                if not ok:
                    return False, err

    elif schema_type == "string":
        if not isinstance(data, str):
            return False, f"{path}: expected string, got {type(data).__name__}"
        min_len = schema.get("minLength")
        if min_len and len(data) < min_len:
            return False, f"{path}: string too short (min {min_len})"

    elif schema_type in ("number", "integer"):
        if not isinstance(data, (int, float)):
            return False, f"{path}: expected number, got {type(data).__name__}"
        if schema_type == "integer" and not isinstance(data, int):
            return False, f"{path}: expected integer"
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and data < minimum:
            return False, f"{path}: value {data} below minimum {minimum}"
        if maximum is not None and data > maximum:
            return False, f"{path}: value {data} above maximum {maximum}"

    elif schema_type == "boolean":
        if not isinstance(data, bool):
            return False, f"{path}: expected boolean, got {type(data).__name__}"

    enum = schema.get("enum")
    if enum is not None and data not in enum:
        return False, f"{path}: value must be one of {enum}"

    return True, ""


async def enforce_schema(
    raw_response: str,
    schema: dict,
    original_prompt: str = "",
) -> dict:
    """
    Try to extract + validate JSON from model response.
    On failure: ask model to fix it (one retry).

    Returns:
      {"valid": True, "data": {...}}
      {"valid": False, "data": None, "raw": "...", "error": "...", "fixed": False}
    """
    # First attempt: extract from raw response
    data = extract_json(raw_response)
    if data is not None:
        valid, error = validate_against_schema(data, schema)
        if valid:
            return {"valid": True, "data": data}
        # Extracted but invalid — try to fix
    else:
        error = "No JSON found in response"

    # Retry: ask model to fix the output
    try:
        from services.inference_service import generate_full_response
        fix_prompt = (
            f"The following response does not match the required JSON schema.\n\n"
            f"Schema:\n{json.dumps(schema, indent=2)}\n\n"
            f"Invalid response:\n{raw_response[:1000]}\n\n"
            f"Error: {error}\n\n"
            f"Fix the response so it is valid JSON matching the schema exactly. "
            f"Output ONLY the corrected JSON, nothing else."
        )
        fixed_text, _, _ = await generate_full_response(
            task="support",
            system_prompt="You are a JSON fixer. Output only valid JSON, nothing else.",
            user_prompt=fix_prompt,
            temperature=0.0,
            max_tokens=1000,
        )
        fixed_data = extract_json(fixed_text)
        if fixed_data is not None:
            valid, error = validate_against_schema(fixed_data, schema)
            if valid:
                return {"valid": True, "data": fixed_data, "fixed": True}
    except Exception:
        pass

    return {
        "valid": False,
        "data": None,
        "raw": raw_response,
        "error": error,
        "fixed": False,
    }
