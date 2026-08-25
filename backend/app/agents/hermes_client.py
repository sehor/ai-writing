"""Compatibility shim: the Hermes boundary now lives in app.integrations.hermes."""

from app.integrations.hermes import (
    HermesAgentClient,
    HermesAgentTransport,
    VirtualHermesAgentServer,
)

__all__ = [
    "HermesAgentClient",
    "HermesAgentTransport",
    "VirtualHermesAgentServer",
]
