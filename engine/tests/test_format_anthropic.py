"""The Anthropic message/tool format adapter.

``to_provider_messages`` / ``to_provider_tools`` produce the Anthropic
content-block / tool schema; ``from_provider_response`` maps the wire response
back to the loop's unified representation. ``tool_use`` blocks survive the round
trip.
"""

from engine.format.anthropic import AnthropicFormat


def test_to_provider_tools_maps_input_schema_key():
    fmt = AnthropicFormat()
    tools = [
        {"name": "cua__click", "description": "click", "inputSchema": {"type": "object"}},
        {"name": "control__todo_write", "description": "todos", "input_schema": {"type": "object"}},
    ]
    out = fmt.to_provider_tools(tools)
    assert out[0] == {
        "name": "cua__click",
        "description": "click",
        "input_schema": {"type": "object"},
    }
    # already-snake input_schema is preserved
    assert out[1]["input_schema"] == {"type": "object"}


def test_to_provider_tools_defaults_missing_schema():
    fmt = AnthropicFormat()
    out = fmt.to_provider_tools([{"name": "t", "description": "d"}])
    assert out[0]["input_schema"] == {"type": "object", "properties": {}}


def test_to_provider_messages_passes_content_blocks_through():
    fmt = AnthropicFormat()
    messages = [
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}],
        },
    ]
    out = fmt.to_provider_messages(messages)
    assert out[0] == {"role": "user", "content": "hello"}
    assert out[1]["content"][0]["type"] == "tool_use"


def test_tool_result_dict_content_is_json_stringified():
    # Anthropic requires tool_result.content to be a string or a list of content
    # blocks -- never a bare object. The MCP dispatch returns a dict, so the
    # adapter must serialize it. (Regression: the live endpoint 400'd on this.)
    fmt = AnthropicFormat()
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": {"secret_word": "rhino"},
                }
            ],
        }
    ]
    out = fmt.to_provider_messages(messages)
    block = out[0]["content"][0]
    assert isinstance(block["content"], str)
    assert "rhino" in block["content"]


def test_tool_result_list_content_blocks_pass_through():
    # A screenshot tool-result (list of content blocks, incl. an image) must
    # survive untouched -- only bare-object content is stringified.
    fmt = AnthropicFormat()
    blocks = [
        {"type": "text", "text": "ok"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "x"}},
    ]
    messages = [
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": blocks}]}
    ]
    out = fmt.to_provider_messages(messages)
    assert out[0]["content"][0]["content"] == blocks


def test_tool_result_string_content_is_left_alone():
    fmt = AnthropicFormat()
    messages = [
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "plain"}]}
    ]
    out = fmt.to_provider_messages(messages)
    assert out[0]["content"][0]["content"] == "plain"


def test_from_provider_response_extracts_content_and_usage():
    fmt = AnthropicFormat()
    wire = {
        "id": "msg_1",
        "role": "assistant",
        "content": [
            {"type": "text", "text": "done"},
            {"type": "tool_use", "id": "t1", "name": "cua__click", "input": {"x": 1}},
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 12, "output_tokens": 5},
    }
    unified = fmt.from_provider_response(wire)
    assert unified["content"] == wire["content"]
    assert unified["usage"] == {"input_tokens": 12, "output_tokens": 5}
    assert unified["stop_reason"] == "tool_use"


def test_tool_use_survives_round_trip():
    fmt = AnthropicFormat()
    wire = {
        "content": [{"type": "tool_use", "id": "t1", "name": "n", "input": {"a": 2}}],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    unified = fmt.from_provider_response(wire)
    tool_uses = [b for b in unified["content"] if b["type"] == "tool_use"]
    assert tool_uses[0]["input"] == {"a": 2}
