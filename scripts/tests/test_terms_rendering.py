"""The packaged terms reach the reader as formatted text, not as markup.

The installer shows `legal/TERMS.rtf` in a Richedit control. That control
renders RTF and nothing else, so every markdown token left in the file is
printed to the reader exactly as written. These tests read the shipped terms and
assert that none survives.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validate_package_inputs import PackageInputError, render_rtf  # noqa: E402

# Written out rather than imported, so these tests still run against a renderer
# that does not define it and report what the reader would actually see.
RTF_HEADER = "{" + r"\rtf1\ansi\deff0\uc1" + " "

TERMS = Path(__file__).resolve().parents[2] / "packaging/inputs/windows-x86_64/legal/TERMS.txt"


def visible_text(rendered: str) -> str:
    """Reduce RTF to the characters a reader sees.

    This is deliberately independent of the renderer: it understands RTF, not
    the shape this project happens to emit, so it still reports the truth if the
    renderer changes.
    """
    assert rendered.startswith(RTF_HEADER) and rendered.endswith("}\n")
    body = rendered[len(RTF_HEADER):-2]
    result: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char in "\r\n":
            # A bare line break is whitespace in RTF and shows nothing.
            index += 1
            continue
        if char in "{}":
            index += 1
            continue
        if char != "\\":
            result.append(char)
            index += 1
            continue
        unicode_escape = re.match(r"\\u(-?[0-9]+)\?", body[index:])
        if unicode_escape:
            result.append(chr(int(unicode_escape.group(1)) % 65536))
            index += unicode_escape.end()
            continue
        literal = re.match(r"\\([\\{}])", body[index:])
        if literal:
            result.append(literal.group(1))
            index += literal.end()
            continue
        control = re.match(r"\\([a-z]+)(-?[0-9]+)? ?", body[index:])
        assert control, f"unknown RTF escape at {body[index:index + 12]!r}"
        result.append({"par": "\n", "tab": "\t", "bullet": "\u2022"}.get(control.group(1), ""))
        index += control.end()
    return "".join(result).encode("utf-16", "surrogatepass").decode("utf-16")


def source_phrases(text: str) -> list[str]:
    """The words of each source block, with every marker removed."""
    phrases = []
    for block in re.split(r"\n\s*\n", text.strip()):
        stripped = re.sub(r"^#{1,6}\s+|^[-*]\s+", "", block.strip(), flags=re.MULTILINE)
        phrases.append(" ".join(stripped.replace("**", "").split()))
    return phrases


def test_no_markdown_token_reaches_the_reader():
    seen = visible_text(render_rtf(TERMS.read_text(encoding="utf-8")).decode("ascii"))
    for token in ("#", "**"):
        assert token not in seen, f"the reader is shown a literal {token!r}"
    for line in seen.splitlines():
        assert not line.startswith("- "), f"the reader is shown a literal bullet marker: {line!r}"


def test_every_source_block_reaches_the_reader_intact():
    text = TERMS.read_text(encoding="utf-8")
    seen = visible_text(render_rtf(text).decode("ascii"))
    flattened = " ".join(seen.replace("\u2022", " ").replace("\t", " ").split())
    missing = [phrase for phrase in source_phrases(text) if phrase not in flattened]
    assert not missing, f"the reader never sees: {missing[:2]}"


def test_a_heading_becomes_bold_and_larger():
    rendered = render_rtf("### Title\n\nBody text.\n").decode("ascii")
    assert re.search(r"\\b\\fs2[0-9] Title\\b0", rendered), rendered
    assert "Title" in visible_text(rendered)


def test_a_bold_span_becomes_a_bold_run():
    rendered = render_rtf("Accept **these terms** now.\n").decode("ascii")
    assert r"{\b these terms}" in rendered
    assert visible_text(rendered).strip() == "Accept these terms now."


def test_a_bullet_becomes_a_bullet():
    rendered = render_rtf("- First\n- Second\n").decode("ascii")
    assert rendered.count(r"\bullet") == 2
    assert visible_text(rendered).splitlines() == ["\u2022\tFirst", "\u2022\tSecond"]


def test_a_wrapped_paragraph_is_rejoined():
    # The source wraps at a fixed width. The reader's window is a different
    # width, so a wrap point must not survive as a line break.
    rendered = render_rtf("One sentence that the source\nwrapped in the middle.\n").decode("ascii")
    assert visible_text(rendered).strip() == "One sentence that the source wrapped in the middle."


def test_a_blank_line_still_separates_paragraphs():
    rendered = render_rtf("First.\n\nSecond.\n").decode("ascii")
    assert visible_text(rendered).splitlines() == ["First.", "Second."]


@pytest.mark.parametrize("text", [
    "Terms {accept} \\ caf\u00e9 \u4e2d\u6587 \U0001f600 end.\n",
    "Plain terms\n",
    "Tabbed\tterms\n",
])
def test_literal_characters_still_survive_escaping(text):
    rendered = render_rtf(text).decode("ascii")
    assert visible_text(rendered).strip() == text.strip()


def test_an_unbalanced_bold_marker_is_refused():
    # Dropping the stray marker hides the mistake and keeping it prints "**",
    # so neither is acceptable.
    with pytest.raises(PackageInputError):
        render_rtf("Accept **these terms now.\n")
