from typing import Protocol

from app.services.push_subscription_service import PushTopic


class PushSender(Protocol):
    """Protocol for sending push notifications to topic subscribers."""

    def send_to_topic_sync(self, topic: PushTopic, title: str, body: str) -> None:
        """Send a push notification to all subscribers of the given topic."""
        ...
