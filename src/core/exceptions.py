from fastapi import HTTPException


class UnsupportedMediaTypeError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=415,
            detail="Неверный формат. Ожидается JPEG, PNG, WEBP",
        )


class PayloadTooLargeError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=413,
            detail="Размер файла превышает лимит",
        )


class ModelNotLoadedError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=503,
            detail="ML модель недоступна",
        )
