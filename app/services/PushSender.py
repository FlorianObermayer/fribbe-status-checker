from typing import Protocol

from app.services.PushSubscriptionService import PushTopic


class PushSender(Protocol):
    def send_to_topic_sync(self, topic: PushTopic, title: str, body: str) -> None: ...
