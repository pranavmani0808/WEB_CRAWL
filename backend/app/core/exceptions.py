from typing import Any, Dict, Optional

class CrawlerException(Exception):
    """Base exception for sitemap-crawler system."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

class DomainValidationError(CrawlerException):
    """Exception raised when domain validation fails."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="DOMAIN_VALIDATION_FAILED", details=details)

class RobotsFetchError(CrawlerException):
    """Exception raised when robots.txt cannot be fetched or parsed."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="ROBOTS_TXT_FAILED", details=details)

class SitemapParseError(CrawlerException):
    """Exception raised when sitemap parsing fails."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="SITEMAP_PARSE_FAILED", details=details)

class HTTPCheckError(CrawlerException):
    """Exception raised during URL status checking."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="HTTP_CHECK_FAILED", details=details)

class AuthenticationError(CrawlerException):
    """Exception raised when authentication fails."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="UNAUTHORIZED", details=details)

class RateLimitExceeded(CrawlerException):
    """Exception raised when rate limits are exceeded."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="RATE_LIMITED", details=details)
