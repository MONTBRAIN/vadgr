"""Tests for the Anthropic vision provider."""

import json
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from computer_use.core.errors import ProviderError
from computer_use.core.types import (
    Action,
    ActionType,
    Element,
    Region,
    ScreenState,
)
from computer_use.providers.anthropic import AnthropicProvider
from computer_use.providers.base import AgentDecision


def make_screen(width=1920, height=1080, image_bytes=b"\x89PNG_fake"):
    return ScreenState(image_bytes=image_bytes, width=width, height=height)


def make_api_response(text):
    return {"content": [{"type": "text", "text": text}]}


def make_urlopen_mock(response_dict):
    body = json.dumps(response_dict).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestCallApi:
    def test_successful_request(self):
        provider = AnthropicProvider(api_key="sk-test-key", model="claude-test")
        expected_response = {"content": [{"type": "text", "text": "hello"}]}
        mock_resp = make_urlopen_mock(expected_response)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result = provider._call_api({"model": "claude-test", "messages": []})

        assert result == expected_response
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert req.get_header("X-api-key") == "sk-test-key"
        assert req.get_header("Content-type") == "application/json"
        assert req.get_header("Anthropic-version") == "2023-06-01"
        assert call_args[1]["timeout"] == 60

    def test_http_error_raises_provider_error(self):
        provider = AnthropicProvider(api_key="sk-test")
        fp = BytesIO(b'{"error": "rate_limited"}')
        http_err = urllib.error.HTTPError(
            url="https://api.anthropic.com/v1/messages",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=fp,
        )

        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(ProviderError, match="429"):
                provider._call_api({"model": "x", "messages": []})

    def test_url_error_raises_provider_error(self):
        provider = AnthropicProvider(api_key="sk-test")
        url_err = urllib.error.URLError("Connection refused")

        with patch("urllib.request.urlopen", side_effect=url_err):
            with pytest.raises(ProviderError, match="connection error"):
                provider._call_api({"model": "x", "messages": []})

    def test_payload_sent_as_json(self):
        provider = AnthropicProvider(api_key="sk-test")
        payload = {"model": "claude-test", "messages": [{"role": "user", "content": "hi"}]}
        mock_resp = make_urlopen_mock({"content": []})

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            provider._call_api(payload)

        req = mock_urlopen.call_args[0][0]
        sent_data = json.loads(req.data.decode("utf-8"))
        assert sent_data == payload


class TestExtractText:
    def test_plain_text(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response('{"action": "click"}')
        assert provider._extract_text(response) == '{"action": "click"}'

    def test_strips_code_fences(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response('```json\n{"action": "click"}\n```')
        assert provider._extract_text(response) == '{"action": "click"}'

    def test_strips_code_fences_no_language(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response('```\n{"x": 1}\n```')
        assert provider._extract_text(response) == '{"x": 1}'

    def test_empty_content(self):
        provider = AnthropicProvider(api_key="sk-test")
        assert provider._extract_text({"content": []}) == ""
        assert provider._extract_text({}) == ""

    def test_skips_non_text_blocks(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = {
            "content": [
                {"type": "image", "data": "..."},
                {"type": "text", "text": "found it"},
            ]
        }
        assert provider._extract_text(response) == "found it"

    def test_strips_whitespace(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response("  hello world  \n")
        assert provider._extract_text(response) == "hello world"


class TestParseAction:
    def test_click(self):
        provider = AnthropicProvider(api_key="sk-test")
        action = provider._parse_action({"action": "click", "x": 100, "y": 200})
        assert action.action_type == ActionType.CLICK
        assert action.x == 100
        assert action.y == 200

    def test_all_action_types(self):
        provider = AnthropicProvider(api_key="sk-test")
        expected = {
            "click": ActionType.CLICK,
            "double_click": ActionType.DOUBLE_CLICK,
            "right_click": ActionType.RIGHT_CLICK,
            "type_text": ActionType.TYPE_TEXT,
            "key_press": ActionType.KEY_PRESS,
            "scroll": ActionType.SCROLL,
            "move": ActionType.MOVE,
            "drag": ActionType.DRAG,
            "wait": ActionType.WAIT,
        }
        for name, action_type in expected.items():
            action = provider._parse_action({"action": name})
            assert action.action_type == action_type

    def test_type_text_carries_text(self):
        provider = AnthropicProvider(api_key="sk-test")
        action = provider._parse_action({"action": "type_text", "text": "hello world"})
        assert action.text == "hello world"
        assert action.action_type == ActionType.TYPE_TEXT

    def test_key_press_carries_keys(self):
        provider = AnthropicProvider(api_key="sk-test")
        action = provider._parse_action({"action": "key_press", "keys": ["ctrl", "s"]})
        assert action.keys == ["ctrl", "s"]

    def test_scroll_carries_amount(self):
        provider = AnthropicProvider(api_key="sk-test")
        action = provider._parse_action({"action": "scroll", "x": 50, "y": 50, "amount": -3})
        assert action.scroll_amount == -3
        assert action.x == 50

    def test_drag_carries_target(self):
        provider = AnthropicProvider(api_key="sk-test")
        action = provider._parse_action({
            "action": "drag", "x": 10, "y": 20, "target_x": 100, "target_y": 200,
        })
        assert action.target_x == 100
        assert action.target_y == 200

    def test_wait_carries_duration(self):
        provider = AnthropicProvider(api_key="sk-test")
        action = provider._parse_action({"action": "wait", "duration": 2.5})
        assert action.duration == 2.5

    def test_unknown_action_raises(self):
        provider = AnthropicProvider(api_key="sk-test")
        with pytest.raises(ProviderError, match="Unknown action type"):
            provider._parse_action({"action": "teleport"})

    def test_empty_action_raises(self):
        provider = AnthropicProvider(api_key="sk-test")
        with pytest.raises(ProviderError, match="Unknown action type"):
            provider._parse_action({})

    def test_defaults_for_optional_fields(self):
        provider = AnthropicProvider(api_key="sk-test")
        action = provider._parse_action({"action": "click"})
        assert action.x is None
        assert action.y is None
        assert action.text is None
        assert action.keys is None
        assert action.scroll_amount == 0
        assert action.duration == 0.0
        assert action.target_x is None
        assert action.target_y is None


class TestParseDecision:
    def test_click_decision(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response(json.dumps({
            "reasoning": "I see the button",
            "action": {"action": "click", "x": 500, "y": 300},
            "confidence": 0.9,
            "error": None,
        }))
        decision = provider._parse_decision(response)
        assert isinstance(decision, AgentDecision)
        assert decision.action.action_type == ActionType.CLICK
        assert decision.action.x == 500
        assert decision.reasoning == "I see the button"
        assert decision.confidence == 0.9
        assert decision.is_task_complete is False
        assert decision.error_detected is None

    def test_done_action_marks_complete(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response(json.dumps({
            "reasoning": "All steps finished",
            "action": {"action": "done"},
            "confidence": 0.95,
        }))
        decision = provider._parse_decision(response)
        assert decision.is_task_complete is True
        assert decision.action.action_type == ActionType.WAIT
        assert decision.action.duration == 0
        assert decision.reasoning == "All steps finished"

    def test_done_without_reasoning_defaults(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response(json.dumps({
            "action": {"action": "done"},
        }))
        decision = provider._parse_decision(response)
        assert decision.reasoning == "Task complete"
        assert decision.confidence == 1.0

    def test_non_done_without_confidence_defaults(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response(json.dumps({
            "action": {"action": "click", "x": 1, "y": 1},
        }))
        decision = provider._parse_decision(response)
        assert decision.confidence == 0.5
        assert decision.reasoning == ""

    def test_error_field_forwarded(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response(json.dumps({
            "reasoning": "something is off",
            "action": {"action": "click", "x": 1, "y": 1},
            "confidence": 0.3,
            "error": "dialog box appeared unexpectedly",
        }))
        decision = provider._parse_decision(response)
        assert decision.error_detected == "dialog box appeared unexpectedly"

    def test_invalid_json_raises(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response("this is not json at all")
        with pytest.raises(ProviderError, match="Cannot parse LLM response"):
            provider._parse_decision(response)

    def test_unknown_action_in_decision_raises(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response(json.dumps({
            "reasoning": "x",
            "action": {"action": "fly_away"},
            "confidence": 0.5,
        }))
        with pytest.raises(ProviderError, match="Unknown action type"):
            provider._parse_decision(response)


class TestParseElement:
    def test_found_element(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response(json.dumps({
            "x": 100, "y": 200, "width": 80, "height": 30,
            "name": "Submit", "role": "button", "confidence": 0.95,
        }))
        elem = provider._parse_element(response)
        assert elem is not None
        assert elem.name == "Submit"
        assert elem.role == "button"
        assert elem.region == Region(x=100, y=200, width=80, height=30)
        assert elem.confidence == 0.95
        assert elem.source == "vision"

    def test_not_found_returns_none(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response(json.dumps({"not_found": True}))
        assert provider._parse_element(response) is None

    def test_invalid_json_returns_none(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response("no json here, sorry")
        assert provider._parse_element(response) is None

    def test_missing_x_returns_none(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response(json.dumps({
            "y": 200, "name": "Submit", "role": "button",
        }))
        assert provider._parse_element(response) is None

    def test_missing_y_returns_none(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response(json.dumps({
            "x": 100, "name": "Submit", "role": "button",
        }))
        assert provider._parse_element(response) is None

    def test_defaults_for_optional_fields(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response(json.dumps({"x": 50, "y": 60}))
        elem = provider._parse_element(response)
        assert elem is not None
        assert elem.name == "unknown"
        assert elem.role == "unknown"
        assert elem.region.width == 50
        assert elem.region.height == 30
        assert elem.confidence == 0.5

    def test_non_numeric_x_returns_none(self):
        provider = AnthropicProvider(api_key="sk-test")
        response = make_api_response(json.dumps({
            "x": "abc", "y": 100, "name": "X", "role": "button",
        }))
        assert provider._parse_element(response) is None


class TestDecideAction:
    def test_builds_payload_and_parses(self):
        provider = AnthropicProvider(api_key="sk-test", model="claude-test")
        screen = make_screen()
        api_response = make_api_response(json.dumps({
            "reasoning": "Clicking the save button",
            "action": {"action": "click", "x": 400, "y": 300},
            "confidence": 0.85,
            "error": None,
        }))
        mock_resp = make_urlopen_mock(api_response)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            decision = provider.decide_action(screen, "Save the file", [])

        assert decision.action.action_type == ActionType.CLICK
        assert decision.action.x == 400
        assert decision.reasoning == "Clicking the save button"

        req = mock_urlopen.call_args[0][0]
        sent = json.loads(req.data.decode("utf-8"))
        assert sent["model"] == "claude-test"
        assert sent["max_tokens"] == 1024

        user_content = sent["messages"][0]["content"]
        assert user_content[0]["type"] == "image"
        assert user_content[0]["source"]["media_type"] == "image/png"
        assert "Save the file" in user_content[1]["text"]
        assert "1920x1080" in user_content[1]["text"]

    def test_includes_elements_when_provided(self):
        provider = AnthropicProvider(api_key="sk-test")
        screen = make_screen()
        elements = [
            Element(name="OK", role="button", region=Region(10, 20, 60, 30), confidence=0.9, source="a11y"),
            Element(name="Cancel", role="button", region=Region(80, 20, 60, 30), confidence=0.8, source="a11y"),
        ]
        api_response = make_api_response(json.dumps({
            "reasoning": "r", "action": {"action": "click", "x": 1, "y": 1}, "confidence": 0.5,
        }))
        mock_resp = make_urlopen_mock(api_response)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            provider.decide_action(screen, "Click OK", [], elements=elements)

        req = mock_urlopen.call_args[0][0]
        sent = json.loads(req.data.decode("utf-8"))
        content_texts = [c["text"] for c in sent["messages"][0]["content"] if c["type"] == "text"]
        element_block = [t for t in content_texts if "UI elements" in t]
        assert len(element_block) == 1
        assert "OK (button)" in element_block[0]
        assert "Cancel (button)" in element_block[0]

    def test_includes_history_when_provided(self):
        provider = AnthropicProvider(api_key="sk-test")
        screen = make_screen()
        history = [
            {"step": 1, "action": "click at (100,200)", "success": True},
            {"step": 2, "action": "type hello", "success": False},
        ]
        api_response = make_api_response(json.dumps({
            "reasoning": "r", "action": {"action": "wait", "duration": 1}, "confidence": 0.5,
        }))
        mock_resp = make_urlopen_mock(api_response)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            provider.decide_action(screen, "Do stuff", history)

        req = mock_urlopen.call_args[0][0]
        sent = json.loads(req.data.decode("utf-8"))
        content_texts = [c["text"] for c in sent["messages"][0]["content"] if c["type"] == "text"]
        history_block = [t for t in content_texts if "Recent actions" in t]
        assert len(history_block) == 1
        assert "Step 1" in history_block[0]
        assert "OK" in history_block[0]
        assert "FAILED" in history_block[0]

    def test_no_elements_no_history_sends_only_image_and_task(self):
        provider = AnthropicProvider(api_key="sk-test")
        screen = make_screen()
        api_response = make_api_response(json.dumps({
            "reasoning": "r", "action": {"action": "done"}, "confidence": 1.0,
        }))
        mock_resp = make_urlopen_mock(api_response)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            provider.decide_action(screen, "Do it", [])

        req = mock_urlopen.call_args[0][0]
        sent = json.loads(req.data.decode("utf-8"))
        content = sent["messages"][0]["content"]
        assert len(content) == 2
        assert content[0]["type"] == "image"
        assert content[1]["type"] == "text"

    def test_history_limited_to_last_five(self):
        provider = AnthropicProvider(api_key="sk-test")
        screen = make_screen()
        history = [{"step": i, "action": f"action_{i}", "success": True} for i in range(10)]
        api_response = make_api_response(json.dumps({
            "reasoning": "r", "action": {"action": "done"}, "confidence": 1.0,
        }))
        mock_resp = make_urlopen_mock(api_response)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            provider.decide_action(screen, "task", history)

        req = mock_urlopen.call_args[0][0]
        sent = json.loads(req.data.decode("utf-8"))
        content_texts = [c["text"] for c in sent["messages"][0]["content"] if c["type"] == "text"]
        history_block = [t for t in content_texts if "Recent actions" in t][0]
        assert "action_0" not in history_block
        assert "action_4" not in history_block
        assert "action_5" in history_block
        assert "action_9" in history_block


class TestLocateElement:
    def test_found(self):
        provider = AnthropicProvider(api_key="sk-test")
        screen = make_screen(width=800, height=600)
        api_response = make_api_response(json.dumps({
            "x": 150, "y": 250, "width": 100, "height": 40,
            "name": "Login", "role": "button", "confidence": 0.88,
        }))
        mock_resp = make_urlopen_mock(api_response)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            elem = provider.locate_element(screen, "the Login button")

        assert elem is not None
        assert elem.name == "Login"
        assert elem.region.x == 150

        req = mock_urlopen.call_args[0][0]
        sent = json.loads(req.data.decode("utf-8"))
        assert sent["max_tokens"] == 512
        text_parts = [c["text"] for c in sent["messages"][0]["content"] if c["type"] == "text"]
        assert any("800x600" in t for t in text_parts)
        assert any("the Login button" in t for t in text_parts)

    def test_not_found(self):
        provider = AnthropicProvider(api_key="sk-test")
        screen = make_screen()
        api_response = make_api_response(json.dumps({"not_found": True}))
        mock_resp = make_urlopen_mock(api_response)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert provider.locate_element(screen, "invisible thing") is None


class TestVerifyAction:
    def test_success(self):
        provider = AnthropicProvider(api_key="sk-test")
        before = make_screen(image_bytes=b"before_img")
        after = make_screen(image_bytes=b"after_img")
        api_response = make_api_response(json.dumps({
            "success": True, "explanation": "The file was saved",
        }))
        mock_resp = make_urlopen_mock(api_response)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            success, explanation = provider.verify_action(before, after, "File should be saved")

        assert success is True
        assert explanation == "The file was saved"

        req = mock_urlopen.call_args[0][0]
        sent = json.loads(req.data.decode("utf-8"))
        assert sent["max_tokens"] == 256
        content = sent["messages"][0]["content"]
        image_blocks = [c for c in content if c["type"] == "image"]
        assert len(image_blocks) == 2

    def test_failure(self):
        provider = AnthropicProvider(api_key="sk-test")
        before = make_screen()
        after = make_screen()
        api_response = make_api_response(json.dumps({
            "success": False, "explanation": "Nothing changed",
        }))
        mock_resp = make_urlopen_mock(api_response)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            success, explanation = provider.verify_action(before, after, "Something should change")

        assert success is False
        assert explanation == "Nothing changed"

    def test_api_error_returns_inconclusive(self):
        provider = AnthropicProvider(api_key="sk-test")
        before = make_screen()
        after = make_screen()

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            success, explanation = provider.verify_action(before, after, "expected change")

        assert success is True
        assert "inconclusive" in explanation.lower()

    def test_bad_json_returns_inconclusive(self):
        provider = AnthropicProvider(api_key="sk-test")
        before = make_screen()
        after = make_screen()
        api_response = make_api_response("not valid json")
        mock_resp = make_urlopen_mock(api_response)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            success, explanation = provider.verify_action(before, after, "expected")

        assert success is True
        assert "inconclusive" in explanation.lower()

    def test_missing_success_defaults_false(self):
        provider = AnthropicProvider(api_key="sk-test")
        before = make_screen()
        after = make_screen()
        api_response = make_api_response(json.dumps({"explanation": "unclear"}))
        mock_resp = make_urlopen_mock(api_response)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            success, explanation = provider.verify_action(before, after, "expected")

        assert success is False
        assert explanation == "unclear"


class TestInit:
    def test_default_model(self):
        provider = AnthropicProvider(api_key="my-key")
        assert provider._api_key == "my-key"
        assert provider._model == "claude-sonnet-4-20250514"

    def test_custom_model(self):
        provider = AnthropicProvider(api_key="key2", model="claude-opus-4-20250514")
        assert provider._model == "claude-opus-4-20250514"
