"""
@file events.py
@brief This file contains the implementation of generic UI event structures.
"""

# Generic UI events structure

class EventSource(object):
    """
    @brief Generate GUI events.
    """
    _events = {}

    @classmethod
    def bind(cls, event, handler):
        """
        @brief Bind an event to a handler.

        @param event The event to bind.
        @param handler The handler function to call when the event is emitted.
        """
        cls._events.setdefault(cls, {}).setdefault(event, []).append(handler)

    def emit(self, event, **data):
        """
        @brief Emit an event and call all bound handlers.

        @param event The event to emit.
        @param data Additional data to pass to the handler functions.
        """
        try:
            for handler in self._events[self.__class__][event]:
                handler(self, **data)
        except KeyError:
            # No handler registered for event.
            pass
