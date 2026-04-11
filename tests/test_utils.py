from pathlib import Path

from bs4 import BeautifulSoup, Tag

import app.dependencies as _deps


def reset_dependency_singletons() -> None:
    """Stop any running pollers and clear all service singletons. Test-only.

    Automatically discovers singletons by the ``_*_service`` naming convention
    in ``app.dependencies``, so no update is needed when new services are added.
    """
    _deps.shutdown()
    for name in vars(_deps):
        if name.startswith("_") and name.endswith("_service"):
            setattr(_deps, name, None)


def read_testdata_from_fs(relative_path: str) -> str:
    with (Path(__file__).parent / relative_path).open(encoding="utf-8") as f:
        return f.read()


def get_weekly_mock_table() -> Tag:
    soup = BeautifulSoup(read_testdata_from_fs("occupancy_weekly_test_data.html"), "html.parser")
    return soup.find("table")  # type: ignore


def get_calendar_mock_table() -> Tag:
    soup = BeautifulSoup(read_testdata_from_fs("occupancy_calendar_test_data.html"), "html.parser")
    return soup.find("table")  # type: ignore
