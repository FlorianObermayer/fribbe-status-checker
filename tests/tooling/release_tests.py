"""Tests for the release script's open-release-branch detection and selection.

Part of the script/tooling suite (``tests/tooling/``) — these tests cover release
tooling rather than the application, and run as a separate pytest invocation.
"""

import pytest

from scripts import release


def test_parse_branch_version() -> None:
    assert release._parse_branch_version("release/v1.2.3") == (1, 2, 3)


def test_parse_branch_version_rejects_non_release_branches() -> None:
    assert release._parse_branch_version("feature/foo") is None
    assert release._parse_branch_version("release/next") is None
    assert release._parse_branch_version("release/v1.2") is None


def test_select_release_branch_returns_none_without_candidates() -> None:
    assert release._select_release_branch([], (0, 5, 8)) is None


def test_select_release_branch_prefers_smallest_jump_above_project() -> None:
    branches = [((0, 5, 10), "release/v0.5.10"), ((0, 5, 9), "release/v0.5.9")]
    assert release._select_release_branch(branches, (0, 5, 8)) == ((0, 5, 9), "release/v0.5.9")


def test_select_release_branch_ignores_lower_versions_when_a_higher_one_exists() -> None:
    branches = [((0, 5, 7), "release/v0.5.7"), ((0, 6, 0), "release/v0.6.0")]
    assert release._select_release_branch(branches, (0, 5, 8)) == ((0, 6, 0), "release/v0.6.0")


def test_select_release_branch_falls_back_to_closest_below_project() -> None:
    branches = [((0, 5, 6), "release/v0.5.6"), ((0, 5, 7), "release/v0.5.7")]
    assert release._select_release_branch(branches, (0, 5, 8)) == ((0, 5, 7), "release/v0.5.7")


def test_release_branch_names_merges_local_and_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_capture(*args: str) -> str:
        if args[-1] == "refs/heads/release/":
            return "release/v0.5.9"
        return "origin/release/v0.5.9\norigin/release/v0.5.10"

    monkeypatch.setattr(release, "_capture", fake_capture)
    # Names are returned in lexicographic order; callers sort by parsed version.
    assert release._release_branch_names() == ["release/v0.5.10", "release/v0.5.9"]


def test_open_release_branches_excludes_merged_and_unnamed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_names() -> list[str]:
        return ["release/v0.5.9", "release/v0.5.10", "release/next"]

    def fake_merged(branch: str) -> bool:
        return branch == "release/v0.5.10"

    monkeypatch.setattr(release, "_release_branch_names", fake_names)
    monkeypatch.setattr(release, "_is_merged_into_main", fake_merged)
    assert release._open_release_branches() == [((0, 5, 9), "release/v0.5.9")]


# ---------------------------------------------------------------------------
# Reuse target resolution
# ---------------------------------------------------------------------------


def test_current_branch_returns_name(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_capture(*_args: str, **_kwargs: str) -> str:
        return "release/v1.2.3"

    monkeypatch.setattr(release, "_capture", _fake_capture)
    assert release._current_branch() == "release/v1.2.3"


def test_current_branch_returns_empty_string_when_detached(monkeypatch: pytest.MonkeyPatch) -> None:
    """A detached HEAD reports the literal 'HEAD', which is not a usable branch name."""

    def _fake_capture(*_args: str, **_kwargs: str) -> str:
        return "HEAD"

    monkeypatch.setattr(release, "_capture", _fake_capture)
    assert release._current_branch() == ""


def test_resolve_reuse_target_prefers_the_checked_out_release_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: on release/v0.5.9 the script must not jump to an open release/v0.5.10."""
    monkeypatch.setattr(release, "_current_branch", lambda: "release/v0.5.9")
    open_branches = [((0, 5, 10), "release/v0.5.10"), ((0, 5, 9), "release/v0.5.9")]
    monkeypatch.setattr(release, "_open_release_branches", lambda: open_branches)
    assert release._resolve_reuse_target((0, 5, 9)) == ((0, 5, 9), "release/v0.5.9")


def test_resolve_reuse_target_uses_current_branch_even_when_not_detected_as_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The current branch wins regardless of the (squash-merge-unreliable) ancestry check."""
    monkeypatch.setattr(release, "_current_branch", lambda: "release/v0.5.9")
    monkeypatch.setattr(release, "_open_release_branches", list)
    assert release._resolve_reuse_target((0, 5, 9)) == ((0, 5, 9), "release/v0.5.9")


def test_resolve_reuse_target_falls_back_to_heuristic_off_a_release_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(release, "_current_branch", lambda: "main")
    monkeypatch.setattr(release, "_open_release_branches", lambda: [((0, 5, 10), "release/v0.5.10")])
    assert release._resolve_reuse_target((0, 5, 9)) == ((0, 5, 10), "release/v0.5.10")


def test_resolve_reuse_target_returns_none_for_non_release_branch_without_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(release, "_current_branch", lambda: "feat/something")
    monkeypatch.setattr(release, "_open_release_branches", list)
    assert release._resolve_reuse_target((0, 5, 9)) is None
