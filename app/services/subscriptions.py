from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone


class SubscriptionService:
    def __init__(self) -> None:
        self._subscriptions: dict[str, set[str]] = defaultdict(set)
        self._events: dict[str, list[dict]] = defaultdict(list)

    def subscribe(self, user_id: str, resource_uri: str) -> dict:
        self._subscriptions[user_id].add(resource_uri)
        return {"subscribed": True, "resource_uri": resource_uri}

    def unsubscribe(self, user_id: str, resource_uri: str) -> dict:
        self._subscriptions[user_id].discard(resource_uri)
        return {"subscribed": False, "resource_uri": resource_uri}

    def emit(self, resource_uri: str, payload: dict) -> None:
        event = {
            "resource_uri": resource_uri,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for user_id, resources in self._subscriptions.items():
            if resource_uri in resources:
                self._events[user_id].append(event)

    def pull_events(self, user_id: str) -> list[dict]:
        events = self._events.get(user_id, [])
        self._events[user_id] = []
        return events

