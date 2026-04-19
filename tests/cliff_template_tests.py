"""Tests for cliff.toml changelog template rendering.

Runs git-cliff as a subprocess (same as CI) against the real cliff.toml
and verifies that the compare link is generated correctly in each scenario.
Requires git-cliff to be available via ``npx git-cliff``.
"""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
CLIFF_TOML = ROOT / "cliff.toml"
_ENV_BASE = {**os.environ, "NODE_OPTIONS": ""}

# Suppress GitHub API calls when no token is available (avoids rate-limit failures
# in local dev). In CI the GITHUB_TOKEN env var is automatically set by GitHub Actions.
_NO_REMOTE: list[str] = [] if os.environ.get("GITHUB_TOKEN") else ["--offline"]


def _run_git_cliff(*extra_args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(  # noqa: S603
        ["npx", "git-cliff", "--config", str(CLIFF_TOML), "--strip", "header", *_NO_REMOTE, *extra_args],  # noqa: S607
        check=True,
        text=True,
        capture_output=True,
        cwd=ROOT,
        env={**_ENV_BASE, **(env or {})},
    )
    return result.stdout


def test_unreleased_with_release_version_shows_compare_link() -> None:
    """--unreleased + RELEASE_VERSION env var produces the compare link."""
    output = _run_git_cliff("--unreleased", env={"RELEASE_VERSION": "v1.2.3"})
    assert "**Full Changelog**:" in output
    assert "...v1.2.3" in output


def test_tagged_release_shows_compare_link() -> None:
    """Passing an explicit --tag produces the compare link using that tag."""
    output = _run_git_cliff("--unreleased", "--tag", "v1.2.3", env={"RELEASE_VERSION": "v1.2.3"})
    assert "**Full Changelog**:" in output
    assert "...v1.2.3" in output


def test_nightly_release_version_used_in_link() -> None:
    """RELEASE_VERSION=nightly appears in the compare link."""
    output = _run_git_cliff("--unreleased", env={"RELEASE_VERSION": "nightly"})
    assert "**Full Changelog**:" in output
    assert "...nightly" in output


def test_no_release_version_omits_compare_link() -> None:
    """Without RELEASE_VERSION the compare link is omitted (no error)."""
    env_without = {k: v for k, v in _ENV_BASE.items() if k != "RELEASE_VERSION"}
    output = _run_git_cliff("--unreleased", env=env_without)
    assert "**Full Changelog**:" not in output


def test_template_renders_without_error() -> None:
    """Template must render without a TemplateParseError or TemplateRenderError."""
    output = _run_git_cliff("--unreleased", env={"RELEASE_VERSION": "v0.0.0"})
    assert "TemplateParseError" not in output
    assert "TemplateRenderError" not in output


def test_unreleased_heading_present() -> None:
    """--unreleased output contains the [Unreleased] heading."""
    output = _run_git_cliff("--unreleased", env={"RELEASE_VERSION": "v0.0.0"})
    assert "[Unreleased]" in output


def test_compare_link_is_valid_github_url() -> None:
    """Compare link points to the correct GitHub compare URL."""
    output = _run_git_cliff("--unreleased", env={"RELEASE_VERSION": "v9.9.9"})
    assert "https://github.com/FlorianObermayer/fribbe-status-checker/compare/" in output
    assert "...v9.9.9" in output
