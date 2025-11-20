import asyncio
import logging
from typing import Callable, Dict, List, Awaitable
from aigent.core.schemas import AgentEvent, EventType

# Type definition for a subscriber function
# It must be an async function that accepts an AgentEvent and returns nothing
Subscriber = Callable[[AgentEvent], Awaitable[None]]

class EventBus:
    """
    An asynchronous event bus that routes AgentEvents to subscribers.
    """
    def __init__(self) -> None:
        self._subscribers: Dict[EventType, List[Subscriber]] = {
            event_type: [] for event_type in EventType
        }
        # Allow subscribing to "all" events via a special key if needed, 
        # but for now we'll keep it explicit.
        self._global_subscribers: List[Subscriber] = []

    def subscribe(self, event_type: EventType, callback: Subscriber) -> None:
        """Register a callback for a specific event type."""
        self._subscribers[event_type].append(callback)

    def subscribe_all(self, callback: Subscriber) -> None:
        """Register a callback for ALL event types."""
        self._global_subscribers.append(callback)

    async def publish(self, event: AgentEvent) -> None:
        """
        Push an event to all relevant subscribers.
        This does NOT block; it schedules the callbacks as tasks.
        """
        callbacks = self._subscribers.get(event.type, []) + self._global_subscribers
        
        if not callbacks:
            return

        # We execute callbacks concurrently using asyncio.gather to ensure speed.
        # If strict ordering is required per-subscriber, this might need adjustment,
        # but for UI updates/logging, concurrent is usually fine and faster.
        
        # We wrap in a try/except block to prevent one bad subscriber from crashing the bus
        tasks = []
        for callback in callbacks:
            tasks.append(self._safe_execute(callback, event))
        
        await asyncio.gather(*tasks)

    async def _safe_execute(self, callback: Subscriber, event: AgentEvent) -> None:
        try:
            await callback(event)
        except Exception as e:
            logging.error(f"Error in event subscriber {callback.__name__}: {e}")
