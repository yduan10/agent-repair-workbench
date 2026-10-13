import pytest


@pytest.fixture
def evidence():
    return {
        "schema_version": 1,
        "tool": {
            "name": "lookup",
            "input_schema": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"],
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "properties": {"count": {"type": "integer"}},
                "required": ["count"],
            },
        },
        "call": {"call_id": "c1", "tool_name": "lookup", "arguments": {"id": 1}},
        "result": {"call_id": "c1", "is_error": False, "structured_content": {"count": 2}},
    }
