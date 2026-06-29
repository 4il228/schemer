import gc
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.endpoints import router
from src.core.config import Settings
from src.services.inference import BlueprintClassifier


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = Settings()
    app.state.classifier = BlueprintClassifier(
        model_path=settings.model_path,
        confidence_threshold=settings.confidence_threshold,
        max_workers=settings.max_workers,
    )
    yield
    app.state.classifier.unload()
    del app.state.classifier
    gc.collect()


app = FastAPI(lifespan=lifespan)
app.include_router(router)
