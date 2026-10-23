"""Keep explicit SPDX copyright statements without inventing ownership."""

from scripts.inspect_legal_crate_sources import statements


def test_spdx_filecopyrighttext_is_retained_verbatim():
    line = '// SPDX-FileCopyrightText: 2024 Example Contributors'
    assert statements(line) == [{'line': 1, 'text': line}]


def test_spdx_absence_markers_are_not_original_ownership():
    assert statements('// SPDX-FileCopyrightText: NONE') == []
    assert statements('// SPDX-FileCopyrightText: NOASSERTION') == []
    assert statements('// SPDX-License-Identifier: MIT') == []
