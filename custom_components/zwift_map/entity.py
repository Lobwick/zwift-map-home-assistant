"""Base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION
from .coordinator import ZwiftMapCoordinator


class ZwiftMapEntity(CoordinatorEntity[ZwiftMapCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: ZwiftMapCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.player_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(coordinator.player_id))},
            name="Zwift Map",
            manufacturer="Zwift (unofficial API)",
            entry_type=DeviceEntryType.SERVICE,
            sw_version=VERSION,
        )
