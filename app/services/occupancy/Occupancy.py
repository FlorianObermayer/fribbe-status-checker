from app.services.occupancy.OccupancySource import OccupancySource
from app.services.occupancy.OccupancyType import OccupancyType


from dataclasses import dataclass
from datetime import datetime


@dataclass
class Occupancy:
    begin: datetime
    end: datetime | None
    event_name: str
    occupancy_type: OccupancyType
    occupancy_source: OccupancySource
    occupied_str: str
