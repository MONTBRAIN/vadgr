

# --- outputs: bytes or 404, never 500 (E2E 0.4.1 F12) ----------------------


def test_a_prose_output_is_returned_as_text_not_crashed_on():
    """This route has two outcomes: the artifact bytes, or 404.

    An output field holds whatever the run produced, and on the native loop
    that is usually the model's prose. It was handed to `Path.resolve()`, which
    raises `OSError: File name too long` past NAME_MAX - so the endpoint
    answered `500` for essentially every free-text output.
    """
    from api.routes.runs import _resolve_output_path, _could_be_a_path

    # A verbatim capture of the model output that caused the defect. Its
    # punctuation is the data under test, not this repo's prose.
    prose = "Executed the sequence: reported progress \"step one\" and \"step two\", wrote a two-item checklist (first done, second pending), and reported progress \"step three\" \u2014 the run is complete.\n\nNote: there is no `update_checklist` or `complete_task` tool available in this environment; I mapped the checklist step to `todo_write` (the only checklist-writing tool) and delivered the completion summary here rather than invoking a nonexistent tool."  # style-check: allow
    assert len(prose.encode()) > 255
    assert _could_be_a_path(prose) is False
    assert _resolve_output_path("", prose) is None      # must not raise


def test_a_plausible_path_is_still_resolved():
    """The guard must not break the case the endpoint exists for."""
    from api.routes.runs import _could_be_a_path

    assert _could_be_a_path("output/run-1/user_outputs/report.md") is True
    assert _could_be_a_path("") is False
