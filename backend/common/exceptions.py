class DataFileUnavailableError(RuntimeError):
    """Raised when a party's configured Parquet file cannot be read."""


class UpstreamServiceError(RuntimeError):
    """Raised when a selected party cannot complete a request."""
