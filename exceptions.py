"""
Custom Exceptions for PRD Creator
X-932: Enhanced error handling with informative messages
"""
import logging
from typing import Optional, Dict, Any

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PRDCreatorError(Exception):
    """Base exception for all PRD Creator errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def log(self) -> None:
        """Log the error with structured details."""
        logger.error(f"{self.__class__.__name__}: {self.message}", extra=self.details)


class PRDGenerationError(PRDCreatorError):
    """Raised when PRD generation fails."""

    def __init__(self, message: str, model: str = "", details: Optional[Dict[str, Any]] = None):
        self.model = model
        details = details or {}
        details["model"] = model
        super().__init__(message, details)


class ModelUnavailableError(PRDGenerationError):
    """Raised when the LLM model is unavailable."""

    def __init__(self, model: str, reason: str = ""):
        message = f"Model '{model}' is unavailable"
        if reason:
            message += f": {reason}"
        super().__init__(message, model=model)


class OCRError(PRDCreatorError):
    """Raised when OCR processing fails."""

    def __init__(self, message: str, file_path: str = "", details: Optional[Dict[str, Any]] = None):
        self.file_path = file_path
        details = details or {}
        details["file_path"] = file_path
        super().__init__(message, details)


class ValidationError(PRDCreatorError):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: str = "", value: Any = "", details: Optional[Dict[str, Any]] = None):
        self.field = field
        self.value = value
        details = details or {}
        if field:
            details["field"] = field
        if value:
            details["value"] = str(value)[:100]  # Truncate long values
        super().__init__(message, details)


class StorageError(PRDCreatorError):
    """Raised when PRD storage operations fail."""

    def __init__(self, message: str, prd_id: str = "", details: Optional[Dict[str, Any]] = None):
        self.prd_id = prd_id
        details = details or {}
        if prd_id:
            details["prd_id"] = prd_id
        super().__init__(message, details)


class RateLimitError(PRDCreatorError):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str, limit: str = "", details: Optional[Dict[str, Any]] = None):
        self.limit = limit
        details = details or {}
        if limit:
            details["limit"] = limit
        super().__init__(message, details)


def handle_error(error: Exception) -> Dict[str, Any]:
    """
    Convert an exception to a user-friendly error response.

    Args:
        error: The exception to handle

    Returns:
        Dictionary with error information suitable for API responses
    """
    # Log the error
    if isinstance(error, PRDCreatorError):
        error.log()
        return {
            "error": error.__class__.__name__,
            "message": error.message,
            "details": error.details
        }
    else:
        logger.exception(f"Unexpected error: {error}")
        return {
            "error": "InternalServerError",
            "message": "An unexpected error occurred",
            "details": {}
        }
