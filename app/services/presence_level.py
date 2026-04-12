from enum import StrEnum


class PresenceLevel(StrEnum):
    """Discrete level of on-site presence."""

    EMPTY = "empty"
    FEW = "few"
    MANY = "many"
