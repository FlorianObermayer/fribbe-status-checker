from enum import Enum

class PresenceLevel(str, Enum):
    EMPTY = "empty"
    FEW = "few"
    MANY = "many"