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


def get_weekly_mock_table() -> Tag:
    soup = BeautifulSoup(read_testdata_from_fs("occupancy_weekly_test_data.html"), "html.parser")
    return soup.find("table")  # pyright: ignore[reportReturnType]


def get_calendar_mock_table() -> Tag:
    soup = BeautifulSoup(read_testdata_from_fs("occupancy_calendar_test_data.html"), "html.parser")
    return soup.find("table")  # pyright: ignore[reportReturnType]
