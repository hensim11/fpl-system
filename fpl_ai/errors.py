"""Domain-specific errors for ingestion failures."""


class FPLDataError(Exception):
    """Base class for errors that should be presented cleanly by the CLI."""


class FPLDownloadError(FPLDataError):
    """Raised when an FPL endpoint cannot be downloaded or decoded."""


class FPLValidationError(FPLDataError):
    """Raised when downloaded data does not satisfy the minimum contract."""
