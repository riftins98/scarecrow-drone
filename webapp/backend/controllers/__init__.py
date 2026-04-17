"""API controller (router) modules. Each handles one domain's HTTP routes."""
from . import sim_controller
from . import flight_controller
from . import drone_controller
from . import area_map_controller
from . import detection_controller
from . import chase_event_controller
from . import connection_controller
from . import static_controller

__all__ = [
    "sim_controller",
    "flight_controller",
    "drone_controller",
    "area_map_controller",
    "detection_controller",
    "chase_event_controller",
    "connection_controller",
    "static_controller",
]
