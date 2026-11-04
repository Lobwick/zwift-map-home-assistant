"""Fixtures for tests that run the integration inside Home Assistant.

Requires ``pytest-homeassistant-custom-component``.
"""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
