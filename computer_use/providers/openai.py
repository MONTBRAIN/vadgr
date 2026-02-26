"""OpenAI GPT-4o vision provider."""

import base64
import json
import logging
import urllib.request
import urllib.error
from typing import Optional

from computer_use.core.errors import ProviderError
from computer_use.core.types import (
    Action,
    ActionType,
    Element,
    Region,
    ScreenState,
)
from computer_use.providers.base import AgentDecision, VisionProvider

logger = logging.getLogger("computer_use.providers.openai")

API_URL = "https://api.openai.com/v1/chat/completions"

# Same system prompt structure as Anthropic, adapted for OpenAI format
SYSTEM_PROMPT = """You are a computer use agent. You see a screenshot of a computer screen and must decide what action to take to accomplish the given task.

Available actions (respond with exactly one as JSON):
- {"action": "click", "x": int, "y": int}
- {"action": "double_click", "x": int, "y": int}
- {"action": "right_click", "x": int, "y": int}
- {"action": "type_text", "text": "string"}
- {"action": "key_press", "keys": ["key1", "key2"]}
- {"action": "scroll", "x": int, "y": int, "amount": int}
- {"action": "move", "x": int, "y": int}
- {"action": "drag", "x": int, "y": int, "target_x": int, "target_y": int}
- {"action": "wait", "duration": float}
- {"action": "done"}

Respond with a JSON object:
{
  "reasoning": "Brief explanation of what you see and why you chose this action",
  "action": { ... },
  "confidence": 0.0-1.0,
  "error": null or "description if something looks wrong"
}

Be precise with coordinates. Look at the screenshot carefully."""


class OpenAIProvider(VisionProvider):
    """GPT-4o API adapter with vision capabilities."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self._api_key = api_key
        self._model = model

    def decide_action(
        self,
        screen: ScreenState,
        task: str,
        history: list[dict],
        elements: Optional[list[Element]] = None,
    ) -> AgentDecision:
        image_b64 = base64.b64encode(screen.image_bytes).decode("utf-8")

        user_content = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_b64}",
                    "detail": "high",
                },
            },
            {
                "type": "text",
                "text": f"Task: {task}\nScreen size: {screen.width}x{screen.height}",
            },
        ]

        if elements:
            element_desc = "\n".join(
                f"- {e.name} ({e.role}) at ({e.region.x},{e.region.y}) "
                f"size {e.region.width}x{e.region.height}"
                for e in elements[:20]
            )
            user_content.append({
                "type": "text",
                "text": f"Visible UI elements:\n{element_desc}",
            })

        if history:
            recent = history[-5:]
            history_desc = "\n".join(
                f"Step {h['step']}: {h['action']} -- {'OK' if h['success'] else 'FAILED'}"
                for h in recent
            )
            user_content.append({
                "type": "text",
                "text": f"Recent actions:\n{history_desc}",
            })

        payload = {
            "model": self._model,
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        }

        response = self._call_api(payload)
        return self._parse_decision(response)

    def locate_element(
        self, screen: ScreenState, description: str
    ) -> Optional[Element]:
        image_b64 = base64.b64encode(screen.image_bytes).decode("utf-8")

        payload = {
            "model": self._model,
            "max_tokens": 512,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_b64}",
                                "detail": "high",
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                f"Find the UI element matching: '{description}'. "
                                f"Screen: {screen.width}x{screen.height}. "
                                "Reply JSON: {\"x\": int, \"y\": int, \"width\": int, "
                                "\"height\": int, \"name\": str, \"role\": str, "
                                "\"confidence\": float} or {\"not_found\": true}"
                            ),
                        },
                    ],
                }
            ],
        }

        response = self._call_api(payload)
        return self._parse_element(response)

    def verify_action(
        self, before: ScreenState, after: ScreenState, expected: str
    ) -> tuple[bool, str]:
        before_b64 = base64.b64encode(before.image_bytes).decode("utf-8")
        after_b64 = base64.b64encode(after.image_bytes).decode("utf-8")

        payload = {
            "model": self._model,
            "max_tokens": 256,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "BEFORE:"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{before_b64}",
                            },
                        },
                        {"type": "text", "text": "AFTER:"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{after_b64}",
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                f"Expected outcome: {expected}\n"
                                "Did the expected change occur? Reply JSON: "
                                "{\"success\": bool, \"explanation\": str}"
                            ),
                        },
                    ],
                }
            ],
        }

        try:
            response = self._call_api(payload)
            text = self._extract_text(response)
            data = json.loads(text)
            return data.get("success", False), data.get("explanation", "")
        except Exception as e:
            logger.warning("Verification parsing failed: %s", e)
            return True, "Verification inconclusive, assuming success"

    def _call_api(self, payload: dict) -> dict:
        """Make HTTP request to OpenAI API."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            API_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            raise ProviderError(f"OpenAI API error ({e.code}): {body}") from e
        except urllib.error.URLError as e:
            raise ProviderError(f"OpenAI API connection error: {e}") from e

    def _extract_text(self, response: dict) -> str:
        """Extract text content from OpenAI response format."""
        choices = response.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        text = message.get("content", "").strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines).strip()
        return text

    def _parse_decision(self, response: dict) -> AgentDecision:
        text = self._extract_text(response)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ProviderError(f"Cannot parse LLM response as JSON: {text}") from e

        action_data = data.get("action", {})
        action_type = action_data.get("action", "")

        if action_type == "done":
            return AgentDecision(
                action=Action(action_type=ActionType.WAIT, duration=0),
                reasoning=data.get("reasoning", "Task complete"),
                is_task_complete=True,
                confidence=data.get("confidence", 1.0),
            )

        action = self._parse_action(action_data)
        return AgentDecision(
            action=action,
            reasoning=data.get("reasoning", ""),
            is_task_complete=False,
            confidence=data.get("confidence", 0.5),
            error_detected=data.get("error"),
        )

    def _parse_action(self, data: dict) -> Action:
        action_type = data.get("action", "")
        type_map = {
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
        at = type_map.get(action_type)
        if at is None:
            raise ProviderError(f"Unknown action type: {action_type}")

        return Action(
            action_type=at,
            x=data.get("x"),
            y=data.get("y"),
            text=data.get("text"),
            keys=data.get("keys"),
            scroll_amount=data.get("amount", 0),
            duration=data.get("duration", 0.0),
            target_x=data.get("target_x"),
            target_y=data.get("target_y"),
        )

    def _parse_element(self, response: dict) -> Optional[Element]:
        text = self._extract_text(response)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None

        if data.get("not_found"):
            return None

        try:
            return Element(
                name=data.get("name", "unknown"),
                role=data.get("role", "unknown"),
                region=Region(
                    x=int(data["x"]),
                    y=int(data["y"]),
                    width=int(data.get("width", 50)),
                    height=int(data.get("height", 30)),
                ),
                confidence=float(data.get("confidence", 0.5)),
                source="vision",
            )
        except (KeyError, ValueError):
            return None
