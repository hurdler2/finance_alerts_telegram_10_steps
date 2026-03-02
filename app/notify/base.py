"""Abstract notifier interface. All delivery adapters must implement this."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class DeliveryResult:
    success: bool
    message_id: str | None = None   # platform-specific message identifier
    error: str | None = None


class BaseNotifier(ABC):
    @abstractmethod
    def send(self, text: str, channel_id: str) -> DeliveryResult:
        """Send a pre-formatted message to the given channel. Returns DeliveryResult."""
        ...
