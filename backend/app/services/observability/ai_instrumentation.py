"""Connect shared Gemini dispatches to the in-process runtime counters."""

from app.services.ai.gateway import (
    GeminiAttemptCompletion,
    GeminiAttemptEvent,
    GeminiAttemptObserver,
)

from .runtime_registry import RuntimeRegistry


def make_gemini_attempt_observer(registry: RuntimeRegistry) -> GeminiAttemptObserver:
    def observe() -> GeminiAttemptCompletion:
        handle = registry.begin_gemini_attempt()

        def complete(event: GeminiAttemptEvent) -> None:
            try:
                if event.outcome != "cancelled":
                    handle.finish(failed=event.outcome != "success")
            finally:
                handle.abandon()

        return complete

    return observe
