"""Action updates use one weekly, credential-free repository policy."""

from pathlib import Path

import pytest


POLICY = Path(__file__).resolve().parents[2] / ".github/dependabot.yml"


def validate_policy(text):
    # An exact minimal shape also excludes registries, credentials and extra ecosystems.
    assert text.splitlines() == [
        "version: 2",
        "updates:",
        '  - package-ecosystem: "github-actions"',
        '    directory: "/"',
        "    schedule:",
        '      interval: "weekly"',
    ]


def test_action_updates_are_weekly_and_need_no_credentials():
    validate_policy(POLICY.read_text(encoding="utf-8"))


@pytest.mark.parametrize("old,new", [
    ("version: 2", "version: 1"),
    ('"github-actions"', '"pip"'),
    ('directory: "/"', 'directory: "/.github/workflows"'),
    ('"weekly"', '"monthly"'),
    ("updates:", "registries: {}\nupdates:"),
    ("updates:", "secrets: {}\nupdates:"),
])
def test_action_update_policy_rejects_missing_or_expanded_boundaries(old, new):
    text = POLICY.read_text(encoding="utf-8")
    assert old in text
    with pytest.raises(AssertionError):
        validate_policy(text.replace(old, new))
