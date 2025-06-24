from enum import Enum


class OccupancyType(str, Enum):
    NONE = "none"
    PARTIALLY = "partially"
    FULLY = "fully"