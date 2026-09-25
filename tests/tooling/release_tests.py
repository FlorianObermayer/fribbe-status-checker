"""Tests for the release script's open-release-branch detection and selection."""

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
