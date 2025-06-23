import os
from bs4 import BeautifulSoup

def get_mock_table_str() -> str:
    with open(
        os.path.join(os.path.dirname(__file__), "occupancy_test_data.html"),
        "r",
        encoding="utf-8",
    ) as f:
        return f.read()

def get_mock_table():
    soup = BeautifulSoup(get_mock_table_str(), "html.parser")
    return soup.find("table")