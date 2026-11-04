"""Binary sensor: is the rider in Zwift right now."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ZwiftMapConfigEntry
from .entity import ZwiftMapEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZwiftMapConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([ZwiftMapRidingSensor(entry.runtime_data)])


class ZwiftMapRidingSensor(ZwiftMapEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:bike"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "riding")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.riding
