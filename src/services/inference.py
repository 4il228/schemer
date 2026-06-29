import asyncio
import io
import time
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
from ultralytics import YOLO


class BlueprintClassifier:
    def __init__(
        self,
        model_path: str,
        confidence_threshold: float,
        max_workers: int,
    ) -> None:
        self.model = YOLO(model_path)
        self.confidence_threshold = confidence_threshold
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def _predict_sync(self, image_bytes: bytes) -> list[dict]:
        image = Image.open(io.BytesIO(image_bytes))
        results = self.model(image)
        detections = []
        for result in results:
            for box in result.boxes:
                score = float(box.conf[0])
                if score >= self.confidence_threshold:
                    detections.append(
                        {
                            "class_id": int(box.cls[0]),
                            "confidence": score,
                        }
                    )
        return detections

    def _apply_decision_matrix(self, detections: list[dict]) -> dict:
        pos_shelves = [d for d in detections if d["class_id"] == 0]
        roughness_symbols = [d for d in detections if d["class_id"] == 1]

        if len(pos_shelves) > 3:
            top_3 = sorted(pos_shelves, key=lambda x: x["confidence"], reverse=True)[:3]
            avg_confidence = sum(d["confidence"] for d in top_3) / len(top_3)
            return {
                "document_type": "Сборочный чертеж (СБ)",
                "confidence": round(avg_confidence, 4),
                "code": "SB",
            }

        if len(pos_shelves) <= 3 and len(roughness_symbols) > 0:
            avg_confidence = sum(d["confidence"] for d in roughness_symbols) / len(
                roughness_symbols
            )
            return {
                "document_type": "Чертеж детали (CD)",
                "confidence": round(avg_confidence, 4),
                "code": "CD",
            }

        return {
            "document_type": "Не определено",
            "confidence": 0.0,
            "code": "UNKNOWN",
        }

    async def predict_async(self, image_bytes: bytes) -> dict:
        loop = asyncio.get_running_loop()
        start_time = time.perf_counter()

        detections = await loop.run_in_executor(
            self.executor, self._predict_sync, image_bytes
        )

        inference_time_ms = round((time.perf_counter() - start_time) * 1000, 1)
        prediction = self._apply_decision_matrix(detections)

        pos_shelves = sum(1 for d in detections if d["class_id"] == 0)
        roughness_symbols = sum(1 for d in detections if d["class_id"] == 1)

        return {
            "prediction": prediction,
            "metrics": {
                "detected_pos_shelves": pos_shelves,
                "detected_roughness_symbols": roughness_symbols,
                "inference_time_ms": inference_time_ms,
            },
        }

    def unload(self) -> None:
        self.executor.shutdown(wait=False)
        del self.model
