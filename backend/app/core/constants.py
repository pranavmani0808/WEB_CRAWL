from enum import Enum

class DomainStatus(str, Enum):
    PENDING = "pending"
    VALIDATING = "validating"
    CRAWLING = "crawling"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"

class SubdomainStatus(str, Enum):
    PENDING = "pending"
    CRAWLED = "crawled"
    FAILED = "failed"

class SitemapStatus(str, Enum):
    PENDING = "pending"
    FETCHING = "fetching"
    FETCHED = "fetched"
    FAILED = "failed"

class SitemapDiscoverySource(str, Enum):
    ROBOTS_TXT = "robots_txt"
    COMMON_LOCATION = "common_location"
    RECURSIVE_DISCOVERY = "recursive_discovery"

class URLCrawlStatus(str, Enum):
    PENDING = "pending"
    CHECKING = "checking"
    CHECKED = "checked"
    FAILED = "failed"

class URLStatusCategory(str, Enum):
    SUCCESS = "success"
    REDIRECT = "redirect"
    CLIENT_ERROR = "client_error"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    DNS_ERROR = "dns_error"
    SSL_ERROR = "ssl_error"
    NETWORK_ERROR = "network_error"

class CrawlJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STOPPING = "stopping"

class ReportType(str, Enum):
    BROKEN_PAGES = "broken_pages"
    REDIRECT_CHAINS = "redirect_chains"
    SLOW_PAGES = "slow_pages"
    DUPLICATE_URLS = "duplicate_urls"
    MISSING_CANONICALS = "missing_canonicals"
    ORPHAN_URLS = "orphan_urls"
    LARGE_PAGES = "large_pages"
    NON_HTML_URLS = "non_html_urls"
    XML_ERRORS = "xml_errors"

class ExportType(str, Enum):
    CSV = "csv"
    JSON = "json"
    EXCEL = "excel"
    SQL = "sql"

class ExportStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"

class LogLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
