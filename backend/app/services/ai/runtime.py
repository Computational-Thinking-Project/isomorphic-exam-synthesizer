"""Lazy app-scoped services. Starting the app does not call or require Gemini."""

from app.core.config import Settings
from app.services.blueprint.service import BlueprintService
from app.services.generation.service import GenerationService

from .gateway import GeminiGateway


class AIRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._gateway: GeminiGateway | None = None
        self._blueprints: BlueprintService | None = None
        self._generation: GenerationService | None = None

    @property
    def gateway(self) -> GeminiGateway:
        if self._gateway is None:
            self._gateway = GeminiGateway(self.settings)
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
        if self._gateway is not None:
            await self._gateway.aclose()
