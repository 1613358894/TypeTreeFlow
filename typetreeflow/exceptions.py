class TypeTreeFlowError(Exception):
    """Base exception for TypeTreeFlow errors."""


class ManifestError(TypeTreeFlowError):
    """Raised when manifest data cannot be read or written safely."""

