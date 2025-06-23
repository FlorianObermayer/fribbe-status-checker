from app.services.occupancy.OccupancyType import OccupancyType


from dataclasses import dataclass
from datetime import datetime


@dataclass
class Occupancy:
    begin: datetime
    end: datetime | None
    event_name: str
    occupancy_type: OccupancyType
    occupied_str: str