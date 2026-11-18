"""The domain errors every importer raises (codes in ARCHITECTURE 9.1). Never carry file content."""

from app import messages
from app.errors import AppError

UNPROCESSABLE = 422


def unsupported_file() -> AppError:
    return AppError("unsupported_file", messages.UNSUPPORTED_FILE, UNPROCESSABLE)


def too_many_rows(max_rows: int) -> AppError:
    return AppError(
        "too_many_rows", messages.TOO_MANY_ROWS, UNPROCESSABLE, details={"max_rows": max_rows}
    )
