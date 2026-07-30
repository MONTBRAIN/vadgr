"""The issue #10 regression guard: keep-last-N screenshot pruning.

A long desktop loop accumulates screenshots in the request body until it
crosses the provider's wire limit and the session dies. Because the native loop
owns the message history, it can prune old screenshots -- keep the last N,
replace the rest with a small text placeholder -- so the body never creeps
toward the limit.
"""

import copy
import json

from engine.loop import PRUNED_PLACEHOLDER_TEXT, prune_old_images


def _image_block(tag: str) -> dict:
    # A heavy base64 image payload -- the only thing that grows the body.
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": tag + ("A" * 5000),
        },
    }


def _history_with_images(count: int) -> list:
    """A realistic history: a user task, then `count` assistant/tool-result
    turns each carrying one screenshot plus tool-result text."""
    messages = [{"role": "user", "content": "do the thing"}]
    for i in range(count):
        messages.append(
            {"role": "assistant", "content": [{"type": "text", "text": f"step {i}"}]}
        )
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": f"t{i}",
                        "content": [
                            {"type": "text", "text": f"result text {i}"},
                            _image_block(f"img{i}-"),
                        ],
                    }
                ],
            }
        )
    return messages


def _collect_image_data(messages: list) -> list:
    found = []
    for msg in messages:
        content = msg["content"]
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "image":
                found.append(block["source"]["data"])
            elif block.get("type") == "tool_result" and isinstance(
                block.get("content"), list
            ):
                for inner in block["content"]:
                    if inner.get("type") == "image":
                        found.append(inner["source"]["data"])
    return found


def test_keeps_last_n_images_intact_and_prunes_the_rest():
    messages = _history_with_images(6)
    keep = 3

    prune_old_images(messages, keep_last=keep)

    remaining = _collect_image_data(messages)
    assert len(remaining) == keep
    # The intact images are the last N (imgs 3, 4, 5).
    assert [d[:6] for d in remaining] == ["img3-A", "img4-A", "img5-A"]


def test_pruned_images_become_the_text_placeholder():
    messages = _history_with_images(5)

    prune_old_images(messages, keep_last=2)

    # The two oldest tool-result turns now carry a placeholder text block in
    # place of the image, not an image block.
    tool_result_0 = messages[2]["content"][0]
    blocks = tool_result_0["content"]
    assert not any(b.get("type") == "image" for b in blocks)
    assert {"type": "text", "text": PRUNED_PLACEHOLDER_TEXT} in blocks


def test_tool_result_text_and_message_order_untouched():
    messages = _history_with_images(4)
    original = copy.deepcopy(messages)

    prune_old_images(messages, keep_last=1)

    # Same number of messages, same roles, same order.
    assert len(messages) == len(original)
    assert [m["role"] for m in messages] == [m["role"] for m in original]
    # Every tool-result text block survives verbatim.
    for i in range(4):
        blocks = messages[2 + i * 2]["content"][0]["content"]
        assert {"type": "text", "text": f"result text {i}"} in blocks


def test_serialized_body_shrinks_below_the_pre_prune_size():
    messages = _history_with_images(10)
    before = len(json.dumps(messages))

    prune_old_images(messages, keep_last=3)

    after = len(json.dumps(messages))
    assert after < before
    # Only 3 heavy payloads remain, not 10.
    assert len(_collect_image_data(messages)) == 3


def test_fewer_images_than_keep_last_is_a_no_op():
    messages = _history_with_images(2)
    original = copy.deepcopy(messages)

    prune_old_images(messages, keep_last=5)

    assert messages == original
