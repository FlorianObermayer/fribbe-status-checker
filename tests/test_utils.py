from pathlib import Path

from bs4 import BeautifulSoup, Tag

import app.dependencies as _deps


class FakePushSender:
    """Test double for push sender used across multiple test files."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def send_to_topic_sync(self, topic: str, title: str, body: str) -> None:
        self.calls.append((topic, title, body))


def reset_dependency_singletons() -> None:
    """Stop any running pollers and clear all service singletons. Test-only."""
    _deps.shutdown()
    svc = _deps._svc
    for attr in vars(svc):
        if not attr.startswith("_"):
            setattr(svc, attr, None)


def read_testdata_from_fs(relative_path: str) -> str:
    with (Path(__file__).parent / relative_path).open(encoding="utf-8") as f:
        return f.read()


def get_latest_snapshot_from_fs(snapshot_path: str) -> str:
    """Return the contents of the latest snapshot file in the given directory."""
    snapshot_dir = Path(__file__).parent / snapshot_path
    snapshot_files = sorted(snapshot_dir.glob("*.html"), reverse=True)
    if not snapshot_files:
        msg = f"No snapshot files found in {snapshot_dir}"
        raise FileNotFoundError(msg)
    latest_snapshot_file = snapshot_files[0]
    with latest_snapshot_file.open(encoding="utf-8") as f:
        return f.read()


def get_weekly_mock_table(relative_snapshot_path: str = "") -> Tag:
    snapshot_path = (
        read_testdata_from_fs(relative_snapshot_path)
        if relative_snapshot_path
        else get_latest_snapshot_from_fs("data/snapshots/occupancy_weekly")
    )
    soup = BeautifulSoup(snapshot_path, "html.parser")
    return soup.find("table")  # pyright: ignore[reportReturnType]


def get_calendar_mock_table(relative_snapshot_path: str = "") -> Tag:
    snapshot_path = (
        read_testdata_from_fs(relative_snapshot_path)
        if relative_snapshot_path
        else get_latest_snapshot_from_fs("data/snapshots/occupancy_calendar")
    )
    soup = BeautifulSoup(snapshot_path, "html.parser")
    return soup.find("table")  # pyright: ignore[reportReturnType]
