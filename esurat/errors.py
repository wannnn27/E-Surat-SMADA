"""Exception domain E-Surat."""

from __future__ import annotations

from typing import Mapping


class DataValidationError(RuntimeError):
    """Data master atau konfigurasi startup tidak aman untuk digunakan."""


class RequestValidationError(ValueError):
    """Request pengguna tidak memenuhi kontrak surat."""

    def __init__(
        self,
        message: str,
        field_errors: Mapping[str, str] | None = None,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.field_errors = dict(field_errors or {})
        self.status_code = status_code
