"""The device class guessed from a zone's name (the panel can't tell a contact from a PIR)."""

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass as C

from custom_components.texecom.binary_sensor import guess_device_class


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Kitchen Ext DoorContact", C.DOOR),  # ptruman's panel (Discussion #1)
        ("Lounge Garden Contact", C.DOOR),
        ("Front Door", C.DOOR),
        ("FrontDoor", C.DOOR),
        ("Garage Door", C.GARAGE_DOOR),
        ("Bedroom Window", C.WINDOW),
        ("WindowContact", C.WINDOW),
        ("Indoor Siren", C.MOTION),
        ("Outdoor PIR", C.MOTION),
        ("Hallway", C.MOTION),
    ],
)
def test_guess_from_name(name, expected):
    assert guess_device_class(name, None) is expected
