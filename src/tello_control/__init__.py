"""tello_control – gesture- and voice-controlled DJI Tello with a hardware-free test stack.

The whole application talks to a single :class:`DroneController` that hides whether
a software mock, a PyBullet physics simulation, or a real Tello is behind it.
"""

__version__ = "0.1.0"

from tello_control.core.controller import DroneController

__all__ = ["DroneController", "__version__"]
