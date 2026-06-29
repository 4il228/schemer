from fastapi import APIRouter, Request, UploadFile

from src.core.config import Settings
from src.core.exceptions import ModelNotLoadedError, PayloadTooLargeError, UnsupportedMediaTypeError

router = APIRouter()
settings = Settings()

SUPPORTED_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"]


@router.get("/health")
async def health(request: Request) -> dict:
    return {
        "status": "healthy",
        "model_loaded": bool(request.app.state.classifier),
        "version": "1.1.0",
    }


@router.post("/api/v1/classify")
async def classify(request: Request, file: UploadFile) -> dict:
    if file.content_type not in SUPPORTED_MIME_TYPES:
        raise UnsupportedMediaTypeError()

    content_length = request.headers.get("content-length")
    if content_length:
        max_bytes = settings.max_file_size_mb * 1024 * 1024
        if int(content_length) > max_bytes:
            raise PayloadTooLargeError()

    if not request.app.state.classifier:
        raise ModelNotLoadedError()

    bytes_data = await file.read()
    result = await request.app.state.classifier.predict_async(bytes_data)

    return {
        "success": True,
        "filename": file.filename,
        "prediction": result["prediction"],
        "metrics": result["metrics"],
    }
