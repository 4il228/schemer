from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_path: str = "models/best.pt"
    max_file_size_mb: int = 15
    confidence_threshold: float = 0.4
    max_workers: int = 4

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }
