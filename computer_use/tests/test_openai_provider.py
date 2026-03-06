"""Tests for the OpenAI GPT-4o vision provider."""

import base64
import io
import json
import urllib.error
import unittest
from unittest.mock import MagicMock, patch

from computer_use.core.errors import ProviderError
from computer_use.core.types import (
    ActionType,
    Element,
    Region,
    ScreenState,
)
from computer_use.providers.openai import OpenAIProvider, API_URL


def make_screen(width=1920, height=1080, image_bytes=b"\x89PNG\r\n"):
    return ScreenState(image_bytes=image_bytes, width=width, height=height)


def openai_response(content: str) -> dict:
    return {
        "choices": [
            {"message": {"content": content}}
        ]
    }


def mock_urlopen(response_dict):
    body = json.dumps(response_dict).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestCallApi(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAIProvider(api_key="sk-test-key", model="gpt-4o")

    @patch("urllib.request.urlopen")
    def test_sends_bearer_auth_header(self, mock_open):
        mock_open.return_value = mock_urlopen({"choices": []})
        self.provider._call_api({"model": "gpt-4o"})

        request_obj = mock_open.call_args[0][0]
        self.assertEqual(request_obj.get_header("Authorization"), "Bearer sk-test-key")
        self.assertEqual(request_obj.get_header("Content-type"), "application/json")

    @patch("urllib.request.urlopen")
    def test_sends_json_payload(self, mock_open):
        mock_open.return_value = mock_urlopen({"choices": []})
        payload = {"model": "gpt-4o", "max_tokens": 512, "messages": []}
        self.provider._call_api(payload)

        request_obj = mock_open.call_args[0][0]
        sent_data = json.loads(request_obj.data.decode("utf-8"))
        self.assertEqual(sent_data, payload)

    @patch("urllib.request.urlopen")
    def test_posts_to_openai_url(self, mock_open):
        mock_open.return_value = mock_urlopen({"choices": []})
        self.provider._call_api({"model": "gpt-4o"})

        request_obj = mock_open.call_args[0][0]
        self.assertEqual(request_obj.full_url, API_URL)

    @patch("urllib.request.urlopen")
    def test_returns_parsed_json(self, mock_open):
        expected = {"choices": [{"message": {"content": "hello"}}]}
        mock_open.return_value = mock_urlopen(expected)
        result = self.provider._call_api({"model": "gpt-4o"})
        self.assertEqual(result, expected)

    @patch("urllib.request.urlopen")
    def test_http_error_raises_provider_error(self, mock_open):
        err = urllib.error.HTTPError(
            url=API_URL, code=429, msg="Too Many Requests",
            hdrs=None, fp=io.BytesIO(b"rate limited"),
        )
        mock_open.side_effect = err

        with self.assertRaises(ProviderError) as ctx:
            self.provider._call_api({"model": "gpt-4o"})
        self.assertIn("429", str(ctx.exception))
        self.assertIn("rate limited", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_url_error_raises_provider_error(self, mock_open):
        mock_open.side_effect = urllib.error.URLError("DNS failure")

        with self.assertRaises(ProviderError) as ctx:
            self.provider._call_api({"model": "gpt-4o"})
        self.assertIn("connection error", str(ctx.exception))


class TestExtractText(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAIProvider(api_key="sk-test", model="gpt-4o")

    def test_extracts_from_choices_message_content(self):
        resp = openai_response('{"action": "click"}')
        self.assertEqual(self.provider._extract_text(resp), '{"action": "click"}')

    def test_returns_empty_on_no_choices(self):
        self.assertEqual(self.provider._extract_text({"choices": []}), "")
        self.assertEqual(self.provider._extract_text({}), "")

    def test_strips_whitespace(self):
        resp = openai_response("  some text  \n")
        self.assertEqual(self.provider._extract_text(resp), "some text")

    def test_strips_code_fences(self):
        fenced = "```json\n{\"x\": 1}\n```"
        resp = openai_response(fenced)
        self.assertEqual(self.provider._extract_text(resp), '{"x": 1}')

    def test_strips_code_fences_without_language(self):
        fenced = "```\n{\"x\": 1}\n```"
        resp = openai_response(fenced)
        self.assertEqual(self.provider._extract_text(resp), '{"x": 1}')

    def test_no_stripping_when_no_fences(self):
        resp = openai_response('{"plain": true}')
        self.assertEqual(self.provider._extract_text(resp), '{"plain": true}')


class TestParseAction(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAIProvider(api_key="sk-test", model="gpt-4o")

    def test_click(self):
        action = self.provider._parse_action({"action": "click", "x": 100, "y": 200})
        self.assertEqual(action.action_type, ActionType.CLICK)
        self.assertEqual(action.x, 100)
        self.assertEqual(action.y, 200)

    def test_type_text(self):
        action = self.provider._parse_action({"action": "type_text", "text": "hello"})
        self.assertEqual(action.action_type, ActionType.TYPE_TEXT)
        self.assertEqual(action.text, "hello")

    def test_key_press(self):
        action = self.provider._parse_action({"action": "key_press", "keys": ["ctrl", "s"]})
        self.assertEqual(action.action_type, ActionType.KEY_PRESS)
        self.assertEqual(action.keys, ["ctrl", "s"])

    def test_scroll(self):
        action = self.provider._parse_action({"action": "scroll", "x": 50, "y": 50, "amount": -3})
        self.assertEqual(action.action_type, ActionType.SCROLL)
        self.assertEqual(action.scroll_amount, -3)

    def test_drag(self):
        data = {"action": "drag", "x": 10, "y": 20, "target_x": 100, "target_y": 200}
        action = self.provider._parse_action(data)
        self.assertEqual(action.action_type, ActionType.DRAG)
        self.assertEqual(action.target_x, 100)
        self.assertEqual(action.target_y, 200)

    def test_wait_with_duration(self):
        action = self.provider._parse_action({"action": "wait", "duration": 2.5})
        self.assertEqual(action.action_type, ActionType.WAIT)
        self.assertAlmostEqual(action.duration, 2.5)

    def test_all_action_types_mapped(self):
        for name in ["click", "double_click", "right_click", "type_text",
                      "key_press", "scroll", "move", "drag", "wait"]:
            action = self.provider._parse_action({"action": name})
            self.assertIsNotNone(action.action_type)

    def test_unknown_action_raises(self):
        with self.assertRaises(ProviderError) as ctx:
            self.provider._parse_action({"action": "fly"})
        self.assertIn("fly", str(ctx.exception))


class TestParseDecision(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAIProvider(api_key="sk-test", model="gpt-4o")

    def test_done_action_marks_complete(self):
        resp = openai_response(json.dumps({
            "reasoning": "all done",
            "action": {"action": "done"},
            "confidence": 0.95,
        }))
        decision = self.provider._parse_decision(resp)
        self.assertTrue(decision.is_task_complete)
        self.assertEqual(decision.action.action_type, ActionType.WAIT)
        self.assertEqual(decision.reasoning, "all done")
        self.assertAlmostEqual(decision.confidence, 0.95)

    def test_click_action_parsed(self):
        resp = openai_response(json.dumps({
            "reasoning": "clicking button",
            "action": {"action": "click", "x": 500, "y": 300},
            "confidence": 0.8,
            "error": None,
        }))
        decision = self.provider._parse_decision(resp)
        self.assertFalse(decision.is_task_complete)
        self.assertEqual(decision.action.action_type, ActionType.CLICK)
        self.assertEqual(decision.action.x, 500)
        self.assertEqual(decision.reasoning, "clicking button")

    def test_error_field_propagated(self):
        resp = openai_response(json.dumps({
            "reasoning": "something wrong",
            "action": {"action": "click", "x": 1, "y": 1},
            "confidence": 0.3,
            "error": "button not visible",
        }))
        decision = self.provider._parse_decision(resp)
        self.assertEqual(decision.error_detected, "button not visible")

    def test_default_confidence_for_non_done(self):
        resp = openai_response(json.dumps({
            "reasoning": "go",
            "action": {"action": "click", "x": 1, "y": 1},
        }))
        decision = self.provider._parse_decision(resp)
        self.assertAlmostEqual(decision.confidence, 0.5)

    def test_invalid_json_raises_provider_error(self):
        resp = openai_response("not json at all")
        with self.assertRaises(ProviderError) as ctx:
            self.provider._parse_decision(resp)
        self.assertIn("Cannot parse", str(ctx.exception))


class TestParseElement(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAIProvider(api_key="sk-test", model="gpt-4o")

    def test_parses_found_element(self):
        resp = openai_response(json.dumps({
            "x": 100, "y": 200, "width": 80, "height": 30,
            "name": "Submit", "role": "button", "confidence": 0.9,
        }))
        elem = self.provider._parse_element(resp)
        self.assertIsNotNone(elem)
        self.assertEqual(elem.name, "Submit")
        self.assertEqual(elem.role, "button")
        self.assertEqual(elem.region.x, 100)
        self.assertEqual(elem.region.y, 200)
        self.assertEqual(elem.region.width, 80)
        self.assertEqual(elem.region.height, 30)
        self.assertAlmostEqual(elem.confidence, 0.9)
        self.assertEqual(elem.source, "vision")

    def test_not_found_returns_none(self):
        resp = openai_response(json.dumps({"not_found": True}))
        self.assertIsNone(self.provider._parse_element(resp))

    def test_invalid_json_returns_none(self):
        resp = openai_response("this is garbage")
        self.assertIsNone(self.provider._parse_element(resp))

    def test_missing_x_y_returns_none(self):
        resp = openai_response(json.dumps({"name": "btn", "role": "button"}))
        self.assertIsNone(self.provider._parse_element(resp))

    def test_default_width_height(self):
        resp = openai_response(json.dumps({"x": 10, "y": 20, "name": "a", "role": "b"}))
        elem = self.provider._parse_element(resp)
        self.assertEqual(elem.region.width, 50)
        self.assertEqual(elem.region.height, 30)

    def test_default_confidence(self):
        resp = openai_response(json.dumps({"x": 10, "y": 20}))
        elem = self.provider._parse_element(resp)
        self.assertAlmostEqual(elem.confidence, 0.5)


class TestDecideAction(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAIProvider(api_key="sk-test-key", model="gpt-4o")

    @patch("urllib.request.urlopen")
    def test_payload_uses_image_url_format(self, mock_open):
        screen = make_screen(image_bytes=b"fakepng")
        api_resp = openai_response(json.dumps({
            "reasoning": "click", "action": {"action": "click", "x": 1, "y": 1},
            "confidence": 0.9,
        }))
        mock_open.return_value = mock_urlopen(api_resp)

        self.provider.decide_action(screen, "test task", [])

        request_obj = mock_open.call_args[0][0]
        payload = json.loads(request_obj.data.decode("utf-8"))

        messages = payload["messages"]
        self.assertEqual(messages[0]["role"], "system")
        user_msg = messages[1]
        self.assertEqual(user_msg["role"], "user")
        image_block = user_msg["content"][0]
        self.assertEqual(image_block["type"], "image_url")
        self.assertIn("data:image/png;base64,", image_block["image_url"]["url"])
        self.assertEqual(image_block["image_url"]["detail"], "high")

    @patch("urllib.request.urlopen")
    def test_image_is_base64_encoded(self, mock_open):
        raw = b"\x89PNG_CONTENT"
        screen = make_screen(image_bytes=raw)
        api_resp = openai_response(json.dumps({
            "reasoning": "r", "action": {"action": "wait", "duration": 0},
            "confidence": 0.9,
        }))
        mock_open.return_value = mock_urlopen(api_resp)

        self.provider.decide_action(screen, "task", [])

        request_obj = mock_open.call_args[0][0]
        payload = json.loads(request_obj.data.decode("utf-8"))
        url = payload["messages"][1]["content"][0]["image_url"]["url"]
        encoded = base64.b64encode(raw).decode("utf-8")
        self.assertTrue(url.endswith(encoded))

    @patch("urllib.request.urlopen")
    def test_includes_screen_dimensions(self, mock_open):
        screen = make_screen(width=2560, height=1440)
        api_resp = openai_response(json.dumps({
            "reasoning": "r", "action": {"action": "done"}, "confidence": 1.0,
        }))
        mock_open.return_value = mock_urlopen(api_resp)

        self.provider.decide_action(screen, "task", [])

        request_obj = mock_open.call_args[0][0]
        payload = json.loads(request_obj.data.decode("utf-8"))
        text_block = payload["messages"][1]["content"][1]
        self.assertIn("2560x1440", text_block["text"])

    @patch("urllib.request.urlopen")
    def test_includes_elements_when_provided(self, mock_open):
        screen = make_screen()
        elem = Element(
            name="OK", role="button",
            region=Region(x=10, y=20, width=60, height=25),
            confidence=0.9, source="accessibility",
        )
        api_resp = openai_response(json.dumps({
            "reasoning": "r", "action": {"action": "click", "x": 10, "y": 20},
            "confidence": 0.9,
        }))
        mock_open.return_value = mock_urlopen(api_resp)

        self.provider.decide_action(screen, "click ok", [], elements=[elem])

        request_obj = mock_open.call_args[0][0]
        payload = json.loads(request_obj.data.decode("utf-8"))
        content_blocks = payload["messages"][1]["content"]
        element_text = content_blocks[2]["text"]
        self.assertIn("OK (button)", element_text)
        self.assertIn("(10,20)", element_text)

    @patch("urllib.request.urlopen")
    def test_includes_history_when_provided(self, mock_open):
        screen = make_screen()
        history = [
            {"step": 1, "action": "click at 100,200", "success": True},
            {"step": 2, "action": "type hello", "success": False},
        ]
        api_resp = openai_response(json.dumps({
            "reasoning": "r", "action": {"action": "wait", "duration": 1},
            "confidence": 0.5,
        }))
        mock_open.return_value = mock_urlopen(api_resp)

        self.provider.decide_action(screen, "task", history)

        request_obj = mock_open.call_args[0][0]
        payload = json.loads(request_obj.data.decode("utf-8"))
        content_blocks = payload["messages"][1]["content"]
        history_text = content_blocks[2]["text"]
        self.assertIn("Step 1", history_text)
        self.assertIn("OK", history_text)
        self.assertIn("FAILED", history_text)

    @patch("urllib.request.urlopen")
    def test_limits_elements_to_20(self, mock_open):
        screen = make_screen()
        elements = [
            Element(
                name=f"elem{i}", role="button",
                region=Region(x=i, y=i, width=10, height=10),
                confidence=0.5, source="vision",
            )
            for i in range(30)
        ]
        api_resp = openai_response(json.dumps({
            "reasoning": "r", "action": {"action": "click", "x": 1, "y": 1},
            "confidence": 0.5,
        }))
        mock_open.return_value = mock_urlopen(api_resp)

        self.provider.decide_action(screen, "task", [], elements=elements)

        request_obj = mock_open.call_args[0][0]
        payload = json.loads(request_obj.data.decode("utf-8"))
        content_blocks = payload["messages"][1]["content"]
        element_text = content_blocks[2]["text"]
        self.assertIn("elem19", element_text)
        self.assertNotIn("elem20", element_text)

    @patch("urllib.request.urlopen")
    def test_limits_history_to_5(self, mock_open):
        screen = make_screen()
        history = [
            {"step": i, "action": f"action_{i}", "success": True}
            for i in range(10)
        ]
        api_resp = openai_response(json.dumps({
            "reasoning": "r", "action": {"action": "done"}, "confidence": 1.0,
        }))
        mock_open.return_value = mock_urlopen(api_resp)

        self.provider.decide_action(screen, "task", history)

        request_obj = mock_open.call_args[0][0]
        payload = json.loads(request_obj.data.decode("utf-8"))
        content_blocks = payload["messages"][1]["content"]
        history_text = content_blocks[2]["text"]
        self.assertNotIn("action_4", history_text)
        self.assertIn("action_5", history_text)
        self.assertIn("action_9", history_text)


class TestLocateElement(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAIProvider(api_key="sk-test", model="gpt-4o")

    @patch("urllib.request.urlopen")
    def test_returns_element_on_success(self, mock_open):
        api_resp = openai_response(json.dumps({
            "x": 300, "y": 400, "width": 100, "height": 40,
            "name": "Search", "role": "text_field", "confidence": 0.85,
        }))
        mock_open.return_value = mock_urlopen(api_resp)

        screen = make_screen()
        elem = self.provider.locate_element(screen, "search box")
        self.assertIsNotNone(elem)
        self.assertEqual(elem.name, "Search")
        self.assertEqual(elem.region.x, 300)

    @patch("urllib.request.urlopen")
    def test_returns_none_when_not_found(self, mock_open):
        api_resp = openai_response(json.dumps({"not_found": True}))
        mock_open.return_value = mock_urlopen(api_resp)

        screen = make_screen()
        self.assertIsNone(self.provider.locate_element(screen, "invisible thing"))

    @patch("urllib.request.urlopen")
    def test_payload_includes_image_url_and_description(self, mock_open):
        api_resp = openai_response(json.dumps({"not_found": True}))
        mock_open.return_value = mock_urlopen(api_resp)

        screen = make_screen(width=800, height=600, image_bytes=b"img")
        self.provider.locate_element(screen, "the OK button")

        request_obj = mock_open.call_args[0][0]
        payload = json.loads(request_obj.data.decode("utf-8"))
        user_content = payload["messages"][0]["content"]
        self.assertEqual(user_content[0]["type"], "image_url")
        text = user_content[1]["text"]
        self.assertIn("the OK button", text)
        self.assertIn("800x600", text)


class TestVerifyAction(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAIProvider(api_key="sk-test", model="gpt-4o")

    @patch("urllib.request.urlopen")
    def test_success_verification(self, mock_open):
        api_resp = openai_response(json.dumps({
            "success": True, "explanation": "dialog closed",
        }))
        mock_open.return_value = mock_urlopen(api_resp)

        before = make_screen(image_bytes=b"before")
        after = make_screen(image_bytes=b"after")
        success, explanation = self.provider.verify_action(before, after, "dialog should close")
        self.assertTrue(success)
        self.assertEqual(explanation, "dialog closed")

    @patch("urllib.request.urlopen")
    def test_failure_verification(self, mock_open):
        api_resp = openai_response(json.dumps({
            "success": False, "explanation": "nothing changed",
        }))
        mock_open.return_value = mock_urlopen(api_resp)

        before = make_screen()
        after = make_screen()
        success, explanation = self.provider.verify_action(before, after, "something")
        self.assertFalse(success)
        self.assertEqual(explanation, "nothing changed")

    @patch("urllib.request.urlopen")
    def test_falls_back_on_parse_error(self, mock_open):
        api_resp = openai_response("totally broken json {{{")
        mock_open.return_value = mock_urlopen(api_resp)

        before = make_screen()
        after = make_screen()
        success, explanation = self.provider.verify_action(before, after, "x")
        self.assertTrue(success)
        self.assertIn("inconclusive", explanation)

    @patch("urllib.request.urlopen")
    def test_falls_back_on_api_error(self, mock_open):
        mock_open.side_effect = urllib.error.URLError("timeout")

        before = make_screen()
        after = make_screen()
        success, explanation = self.provider.verify_action(before, after, "x")
        self.assertTrue(success)
        self.assertIn("inconclusive", explanation)

    @patch("urllib.request.urlopen")
    def test_payload_has_both_images(self, mock_open):
        api_resp = openai_response(json.dumps({"success": True, "explanation": "ok"}))
        mock_open.return_value = mock_urlopen(api_resp)

        before = make_screen(image_bytes=b"BEFORE_IMG")
        after = make_screen(image_bytes=b"AFTER_IMG")
        self.provider.verify_action(before, after, "expected change")

        request_obj = mock_open.call_args[0][0]
        payload = json.loads(request_obj.data.decode("utf-8"))
        content = payload["messages"][0]["content"]

        image_urls = [
            block["image_url"]["url"]
            for block in content
            if block.get("type") == "image_url"
        ]
        self.assertEqual(len(image_urls), 2)
        before_b64 = base64.b64encode(b"BEFORE_IMG").decode("utf-8")
        after_b64 = base64.b64encode(b"AFTER_IMG").decode("utf-8")
        self.assertIn(before_b64, image_urls[0])
        self.assertIn(after_b64, image_urls[1])


class TestConstructor(unittest.TestCase):
    def test_default_model(self):
        p = OpenAIProvider(api_key="key")
        self.assertEqual(p._model, "gpt-4o")

    def test_custom_model(self):
        p = OpenAIProvider(api_key="key", model="gpt-4-turbo")
        self.assertEqual(p._model, "gpt-4-turbo")

    def test_stores_api_key(self):
        p = OpenAIProvider(api_key="sk-abc123")
        self.assertEqual(p._api_key, "sk-abc123")


if __name__ == "__main__":
    unittest.main()
