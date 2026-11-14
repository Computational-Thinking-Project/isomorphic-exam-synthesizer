"""Lazy app-scoped services. Starting the app does not call or require Gemini."""

import logging

from app.core.config import Settings
from app.services.blueprint.service import BlueprintService
from app.services.generation.service import GenerationService

from .gateway import GeminiAttemptObserver, GeminiGateway

logger = logging.getLogger(__name__)


class AIRuntime:
    def __init__(
        self, settings: Settings, *, attempt_observer: GeminiAttemptObserver | None = None
    ):
        self.settings = settings
        self._attempt_observer = attempt_observer
        self._gateway: GeminiGateway | None = None
        self._blueprints: BlueprintService | None = None
        self._generation: GenerationService | None = None

    @property
    def gateway(self) -> GeminiGateway:
        if self._gateway is None:
            self._gateway = GeminiGateway(self.settings, attempt_observer=self._attempt_observer)
        return self._gateway

    @property
    def blueprints(self) -> BlueprintService:
        if self._blueprints is None:
            self._blueprints = BlueprintService(self.gateway)
        return self._blueprints

    @property
    def generation(self) -> GenerationService:
        if self._generation is None:
            self._generation = GenerationService(self.gateway)
        return self._generation

    async def aclose(self) -> None:
        if self._generation is not None:
            if not await self._generation.validator.aclose(timeout_seconds=10):
                logger.error("Validator workers exceeded the shutdown cleanup budget.")
        if self._gateway is not None:
            await self._gateway.aclose()
