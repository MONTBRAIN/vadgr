"""The capture helper must report how much of an image is one flat colour.

A capture that is entirely one colour is refused, because it is certainly
unrendered. A capture that is mostly one colour is not refused, because that
can be the correct and only view of a window no single flag renders whole. It
has to be reported, because an unreported partial frame once reached an
evidence boundary as a finished one.

These tests use synthetic images rather than a live window, so they run on any
host. The measured behaviour they encode came from the installer bootstrapper
on 2026-10-23.
"""

import pathlib
import sys

import pytest

from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from windows_uia import flat_share  # noqa: E402


def solid(width, height, colour):
    return Image.new("RGB", (width, height), colour)


def painted(width, height, background, foreground, covered_rows):
    """One surface where only part of the area carries content."""
    image = solid(width, height, background)
    for y in range(covered_rows):
        for x in range(width):
            image.putpixel((x, y), foreground)
    return image


def test_an_entirely_flat_image_is_reported_as_entirely_flat():
    assert flat_share(solid(40, 30, (255, 255, 255))) == 1.0
    assert flat_share(solid(40, 30, (0, 0, 0))) == 1.0


def test_a_fully_painted_image_is_not_mostly_one_colour():
    image = painted(40, 30, (255, 255, 255), (0, 0, 0), 15)
    assert flat_share(image) == pytest.approx(0.5)


def test_a_mostly_blank_frame_is_reported_rather_than_hidden():
    # The shape the bootstrapper produced with the flag that carries only the
    # child controls: a little content and a large flat area.
    image = painted(100, 100, (255, 255, 255), (0, 0, 0), 4)
    share = flat_share(image)
    assert share == pytest.approx(0.96)
    # It is high enough that a reader must be told, and not 1.0, so the helper
    # must not refuse it.
    assert 0.9 < share < 1.0


def test_the_share_is_a_proportion_of_every_pixel():
    for width, height in ((1, 1), (3, 7), (64, 48)):
        assert 0.0 < flat_share(solid(width, height, (12, 34, 56))) <= 1.0


def test_an_empty_image_counts_as_flat():
    assert flat_share(Image.new("RGB", (0, 0))) == 1.0


def test_an_image_with_many_colours_is_not_dominated_by_one():
    image = Image.new("RGB", (16, 16))
    for y in range(16):
        for x in range(16):
            image.putpixel((x, y), (x * 16, y * 16, (x + y) * 8))
    # Every pixel differs, so no colour holds more than one pixel of 256.
    assert flat_share(image) == pytest.approx(1 / 256)


def test_the_docstring_records_what_was_measured_rather_than_the_old_claim():
    source = (pathlib.Path(__file__).resolve().parent / "windows_uia.py").read_text(
        encoding="utf-8"
    )
    # The old docstring told the reader that the bootstrapper returns an empty
    # client with PW_RENDERFULLCONTENT. It does not, and following that claim
    # produced the partly painted frame one pass filed as unexplained.
    assert "returns an empty client when it *is*" not in source
    assert "neither flag is enough" in source
    assert "flat_share" in source
