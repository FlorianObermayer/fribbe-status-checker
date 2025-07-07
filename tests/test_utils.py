import os
from bs4 import BeautifulSoup, Tag


def read_testdata_from_fs(relative_path: str) -> str:
    with open(
        os.path.join(os.path.dirname(__file__), relative_path),
        "r",
        encoding="utf-8",
    ) as f:
        return f.read()


def get_weekly_mock_table() -> Tag:
    soup = BeautifulSoup(
        read_testdata_from_fs("occupancy_weekly_test_data.html"), "html.parser"
    )
    return soup.find("table")  # type: ignore


def get_calendar_mock_table() -> Tag:
    soup = BeautifulSoup(
        read_testdata_from_fs("occupancy_calendar_test_data.html"), "html.parser"
    )
    return soup.find("table")  # type: ignore
