"""Create a release branch and open a pull request against main.

Refreshes the lock file and licenses, bumps the version, pushes the release branch and opens a PR.

Usage:
    uv run release                  # analyse commits, suggest bump, prompt to confirm
    uv run release patch            # skip prompt, use patch
    uv run release minor            # skip prompt, use minor
    uv run release major            # skip prompt, use major
    uv run release --dry-run        # show what would happen without doing anything
    uv run release minor --dry-run  # dry-run with explicit bump type
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from scripts.generate_licenses import main as _generate_licenses

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
_VERSION_RE = re.compile(r'^(version\s*=\s*")(\d+)\.(\d+)\.(\d+)(")', re.MULTILINE)
_REPO = "FlorianObermayer/fribbe-status-checker"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Subprocess environment with NODE_OPTIONS cleared to prevent devcontainer
# Node.js flags (e.g. --openssl-legacy-provider) from interfering with git.
_ENV = {**os.environ, "NODE_OPTIONS": ""}


def _run(*args: str, check: bool = True, dry_run: bool = False) -> subprocess.CompletedProcess[str]:
    if dry_run:
        print(f"[dry-run] {' '.join(args)}")
        return subprocess.CompletedProcess(args, 0)
    return subprocess.run(list(args), check=check, text=True, cwd=ROOT, env=_ENV)


def _capture(*args: str, check: bool = True) -> str:
    result = subprocess.run(list(args), check=check, text=True, capture_output=True, cwd=ROOT, env=_ENV)
    return result.stdout.strip()


def _current_version(text: str) -> tuple[int, int, int]:
    m = _VERSION_RE.search(text)
    if not m:
        sys.exit('error: could not find version = "x.y.z" in pyproject.toml')
    return int(m.group(2)), int(m.group(3)), int(m.group(4))


def _bump(major: int, minor: int, patch: int, part: str) -> tuple[int, int, int]:
    if part == "major":
        return major + 1, 0, 0
    if part == "minor":
        return major, minor + 1, 0
    return major, minor, patch + 1


def _branch_exists_local(branch: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{branch}"],
        check=False,
        capture_output=True,
        cwd=ROOT,
    )
    return result.returncode == 0


def _branch_exists_remote(branch: str) -> bool:
    return bool(_capture("git", "ls-remote", "--heads", "origin", branch))


def _dirty_files() -> list[str]:
    """Return relative paths of files with unstaged changes."""
    return _capture("git", "diff", "--name-only").splitlines()


def _github_api(method: str, path: str, token: str, body: dict[str, object] | None = None) -> Any:
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _find_open_pr(branch: str, token: str) -> str | None:
    try:
        prs = _github_api("GET", f"/repos/{_REPO}/pulls?state=open&head=FlorianObermayer:{branch}", token)
        if prs:
            return str(prs[0]["html_url"])
    except urllib.error.HTTPError:
        pass
    return None


def _commits_since_last_tag() -> str:
    last_tag = _capture("git", "describe", "--tags", "--abbrev=0", check=False)
    if last_tag:
        return _capture("git", "log", f"{last_tag}..HEAD", "--oneline")
    return _capture("git", "log", "--oneline", "-20")


_BREAKING_RE = re.compile(r"^\w+(?:\(\w+\))?!:|BREAKING[- ]CHANGE", re.MULTILINE)
_FEAT_RE = re.compile(r"^feat(?:\(\w+\))?:", re.MULTILINE)


def _suggest_bump_type() -> tuple[str, str]:
    """Return (suggested_bump_type, formatted_commit_list)."""
    commits = _commits_since_last_tag()
    if _BREAKING_RE.search(commits):
        return "major", commits
    if _FEAT_RE.search(commits):
        return "minor", commits
    return "patch", commits


def _prompt_bump_type(suggestion: str, commits: str) -> str:
    """Print unreleased commits, show suggestion, return confirmed or overridden bump type."""
    if commits:
        print("\nUnreleased commits:")
        for line in commits.splitlines():
            print(f"  {line}")
    else:
        print("\nNo commits found since last tag.")
    print(f"\nSuggested bump: {suggestion}")
    answer = input(f"Bump type [ENTER to accept '{suggestion}', or type patch/minor/major]: ").strip().lower()
    if not answer:
        return suggestion
    if answer not in ("patch", "minor", "major"):
        sys.exit(f"error: unknown bump type '{answer}' — use patch, minor, or major")
    return answer


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(prog="uv run release", description="Create a release branch and PR.")
    parser.add_argument("bump", nargs="?", choices=["patch", "minor", "major"], help="Version bump type")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without making any changes")
    args = parser.parse_args()
    dry_run: bool = args.dry_run

    if dry_run:
        print("[dry-run] no files will be written, no commits made, no push, no PR")

    load_dotenv(ROOT / "scripts" / ".env")

    # 1. Abort if working tree has uncommitted changes
    unstaged = subprocess.run(["git", "diff", "--quiet"], check=False, cwd=ROOT, env=_ENV)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False, cwd=ROOT, env=_ENV)
    if not dry_run and (unstaged.returncode != 0 or staged.returncode != 0):
        sys.exit("error: working tree has uncommitted changes — commit or stash them first")

    # 2. Determine bump type — analyse commits and prompt if not passed as argument
    if args.bump:
        part = args.bump
    else:
        suggestion, commits = _suggest_bump_type()
        part = _prompt_bump_type(suggestion, commits)

    # 3. Compute new version
    text = PYPROJECT.read_text()
    major, minor, patch = _current_version(text)
    new_major, new_minor, new_patch = _bump(major, minor, patch, part)
    old_ver = f"{major}.{minor}.{patch}"
    new_ver = f"{new_major}.{new_minor}.{new_patch}"
    branch = f"release/v{new_ver}"
    print(f"  version : {old_ver} \u2192 {new_ver}")
    print(f"  branch  : {branch}")

    # 3. Create or check out release branch
    if _branch_exists_local(branch):
        print(f"[branch] checking out existing local branch {branch}")
        _run("git", "checkout", branch, dry_run=dry_run)
    elif _branch_exists_remote(branch):
        print(f"[branch] fetching and checking out remote branch {branch}")
        _run("git", "fetch", "origin", branch, dry_run=dry_run)
        _run("git", "checkout", "-b", branch, f"origin/{branch}", dry_run=dry_run)
    else:
        print("[branch] updating main before branching ...")
        _run("git", "checkout", "main", dry_run=dry_run)
        _run("git", "pull", "--ff-only", "origin", "main", dry_run=dry_run)
        print(f"[branch] creating {branch}")
        _run("git", "checkout", "-b", branch, dry_run=dry_run)

    # 4. Write new version to pyproject.toml (no commit yet)
    new_text = _VERSION_RE.sub(rf"\g<1>{new_major}.{new_minor}.{new_patch}\g<5>", text)
    if dry_run:
        print(f"[dry-run] write pyproject.toml: version {old_ver} \u2192 {new_ver}")
    else:
        PYPROJECT.write_text(new_text)

    # 5. Refresh lock file
    print("[sync] uv sync --all-groups ...")
    _run("uv", "sync", "--all-groups", dry_run=dry_run)

    # 6. Refresh licenses
    print("[licenses] generate-licenses ...")
    if not dry_run:
        _generate_licenses()
    else:
        print("[dry-run] generate-licenses()")

    # 7. Commit uv.lock / app/licenses.json if either changed
    support = [f for f in _dirty_files() if f in ("uv.lock", "app/licenses.json")]
    if support:
        print(f"[commit] {', '.join(support)}")
        _run("git", "add", *support, dry_run=dry_run)
        _run("git", "commit", "-m", f"chore: update lock file and licenses for v{new_ver}", dry_run=dry_run)

    # 8. Commit version bump
    _run("git", "add", "pyproject.toml", dry_run=dry_run)
    _run("git", "commit", "-m", f"chore(release): v{new_ver}", dry_run=dry_run)
    print(f"[commit] chore(release): v{new_ver}")

    # 9. Push branch
    _run("git", "push", "--set-upstream", "origin", branch, dry_run=dry_run)
    print(f"[push] {branch} \u2192 origin")

    # 10. Create PR
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("\n[pr] no GITHUB_TOKEN found \u2014 skipping PR creation")
        print(f"     open manually: https://github.com/{_REPO}/compare/{branch}")
        return

    if dry_run:
        print(f"[dry-run] would create PR: chore(release): v{new_ver} ({branch} \u2192 main)")
        return

    existing = _find_open_pr(branch, token)
    if existing:
        print(f"\n[pr] already exists: {existing}")
        return

    commits = _commits_since_last_tag()
    body = (
        f"## Release v{new_ver}\n\n"
        "### Changes since last release\n\n"
        f"```\n{commits}\n```\n\n"
        f"Merging to `main` will trigger the CI/CD pipeline and create a stable GitHub release tagged `v{new_ver}`.\n"
    )

    try:
        pr = _github_api(
            "POST",
            f"/repos/{_REPO}/pulls",
            token,
            {
                "title": f"chore(release): v{new_ver}",
                "head": branch,
                "base": "main",
                "body": body,
            },
        )
        print(f"\n[pr] created: {pr['html_url']}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        print(f"\n[pr] warning: could not create PR ({e.code}): {detail}", file=sys.stderr)
        print(f"     open manually: https://github.com/{_REPO}/compare/{branch}")


if __name__ == "__main__":
    main()
