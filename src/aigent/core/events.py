"""The Core Event Bus and Dispatcher.

This module implements the "Handles" pattern, providing a centralized
event bus with dynamic dependency injection for handlers.
"""

import asyncio
import inspect
import logging
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union

try:
    from enum import StrEnum  # Python 3.11+
except ImportError:
    from strenum import StrEnum  # Fallback

from aigent.core.logging import get_logger

logger = get_logger(__name__)

# --- Core Signals ---

class CoreSignal(StrEnum):
    """Built-in signals used by the core system."""
    # Client Lifecycle
    CLIENT_CONNECT = "client:connect"
    CLIENT_DISCONNECT = "client:disconnect"
    
    # Input/Output
    CLIENT_INPUT_RECEIVED = "client:input_received"  # User typed something
    SYSTEM_OUTPUT = "system:output"                  # System wants to send to client
    
    # Session
    SESSION_START = "session:start"
    SESSION_RENAME = "session:rename"
    SESSION_RENAMED = "session:renamed"
    
    # Errors
    SYSTEM_ERROR = "system:error"

# --- Dispatcher Logic ---

@dataclass
class Handler:
    """Represents a registered event handler."""
    func: Callable[..., Any]
    priority: int
    event_name: str
    
    @property
    def name(self) -> str:
        return self.func.__name__

PRIMITIVES = (int, float, str, bool, bytes, dict, list, tuple, set, type(None))

class Dispatcher:
    """The central event bus.
    
    Manages registration of handlers and dispatching of events with
    dependency injection.
    """
    
    def __init__(self) -> None:
        self._handlers: Dict[str, List[Handler]] = defaultdict(list)
        self._known_signals: List[Type[StrEnum]] = [CoreSignal]

    def register_signals(self, enum_class: Type[StrEnum]) -> None:
        """Register a Signal Enum for introspection/cataloging."""
        if enum_class not in self._known_signals:
            self._known_signals.append(enum_class)

    def register(self, event_name: Union[str, StrEnum], func: Callable[..., Any], priority: int = 0) -> None:
        """Register a function as a handler for an event."""
        name = str(event_name)
        handler = Handler(func, priority, name)
        self._handlers[name].append(handler)
        # Sort high priority first
        self._handlers[name].sort(key=lambda x: x.priority, reverse=True)
        logger.debug(f"Registered handler '{func.__name__}' for '{name}' (p={priority})")

    async def dispatch(self, event_name: Union[str, StrEnum], **context: Any) -> None:
        """Dispatch an event to all registered handlers.
        
        Args:
            event_name: The signal to fire.
            **context: The data payload (dependencies) to inject into handlers.
        """
        name = str(event_name)
        logger.debug(f"Dispatching '{name}' with context keys: {list(context.keys())}")
        
        # Get handlers for this event + wildcards (future feature?)
        handlers = self._handlers.get(name, [])
        
        if not handlers:
            logger.debug(f"No handlers found for '{name}'")
            return

        # Inject 'bus' and 'event_name' into context if not present
        if "bus" not in context:
            context["bus"] = self
        if "event_name" not in context:
            context["event_name"] = name

        results = []
        
        for handler in handlers:
            try:
                # Dependency Injection
                kwargs = self._match_parameters(handler.func, context)
                
                # Execution
                if inspect.iscoroutinefunction(handler.func):
                    res = await handler.func(**kwargs)
                else:
                    res = handler.func(**kwargs)
                
                results.append(res)
                
            except Exception as e:
                logger.error(f"Error in handler '{handler.name}': {e}", exc_info=True)
                # Avoid infinite loops if the error handler itself fails
                if name != CoreSignal.SYSTEM_ERROR:
                    await self.dispatch(
                        CoreSignal.SYSTEM_ERROR, 
                        exception=e, 
                        original_event=name, 
                        original_context=context
                    )

    def _match_parameters(self, func: Callable[..., Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Inject dependencies based on name and type signature.
        
        Adapted from the robust matching logic in DevAPI.
        
        Rules:
        1. Objects > Primitives.
        2. Primitives MUST match by name.
        3. Objects can match by Type or Name.
        """
        sig = inspect.signature(func)
        kwargs: Dict[str, Any] = {}
        missing: List[str] = []
        
        for param_name, param in sig.parameters.items():
            # Skip **kwargs arguments in the handler signature
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                continue
                
            # 1. Try Name Match (Highest Precedence for Primitives)
            if param_name in context:
                val = context[param_name]
                # If annotation exists, verify type? (Optional strictness)
                kwargs[param_name] = val
                continue
            
            # 2. Try Type Match (For Objects Only)
            annotation = param.annotation
            if annotation != inspect.Parameter.empty and not self._is_primitive(annotation):
                match_found = False
                for ctx_val in context.values():
                    if isinstance(ctx_val, annotation):
                        kwargs[param_name] = ctx_val
                        match_found = True
                        break
                if match_found:
                    continue
            
            # 3. Handle Missing
            if param.default == inspect.Parameter.empty:
                missing.append(f"{param_name}: {annotation}")

        # If strict matching failed for required args, log loudly (Loud Failure)
        if missing:
            logger.debug(
                f"Skipping handler '{func.__name__}'. Missing required dependencies: {missing}. "
                f"Available context keys: {list(context.keys())}"
            )
            raise TypeError(f"Missing dependencies: {missing}")
            
        return kwargs

    def _is_primitive(self, type_hint: Any) -> bool:
        """Check if a type hint is a primitive."""
        # Handle simple types
        if type_hint in PRIMITIVES:
            return True
        # Handle Optionals/Unions? Simplified for now.
        return False

# Singleton Bus
bus = Dispatcher()

# Decorator
def handles(event_name: Union[str, StrEnum], priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to register a function as an event handler."""
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        bus.register(event_name, func, priority)
        return func
    return decorator

def register_signals(enum_class: Type[StrEnum]) -> None:
    """Helper to register signal enums."""
    bus.register_signals(enum_class)
