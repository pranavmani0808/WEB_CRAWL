"""Core crawler engine coordinating the crawling process stages"""
import asyncio
import socket
import ssl
import time
import uuid
import logging
import hashlib
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse

import httpx

from app.core.constants import (
    CrawlJobStatus, DomainStatus, SitemapStatus,
    SitemapDiscoverySource, URLCrawlStatus, URLStatusCategory
)
from app.models.domain import Domain
from app.models.subdomain import Subdomain
from app.models.sitemap import Sitemap
from app.models.url import URL
from app.models.crawl_job import CrawlJob
from app.models.crawl_log import CrawlLog
from app.models.crawl_statistics import CrawlStatistics
from app.models.report import Report
from app.models.url_snapshot import UrlSnapshot
from app.core.config import settings
from app.crawler.rate_limiter import RateLimiter
from app.crawler.seo_extractor import SEOExtractor
from app.crawler.sitemap_parser import SitemapParser
from app.crawler.issue_detector import IssueDetector
from app.crawler.js_renderer import JsRenderer, looks_js_rendered

logger = logging.getLogger(__name__)

# httpx's default User-Agent ("python-httpx/x.y.z") gets blocked outright by most
# WAFs/bot-protection (Cloudflare, Vercel, etc.) even for public pages. A standard
# browser UA plus the headers a real browser sends avoids that false-positive block.
DEFAULT_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def get_url_hash(url: str) -> str:
    return hashlib.sha256(url.encode('utf-8')).hexdigest()


class CrawlCancelledError(Exception):
    """Raised internally when a user has asked a running crawl to stop.

    Caught once in CrawlerEngine.execute() to do the actual status/cleanup -
    see _check_cancelled for where this gets raised.
    """
    pass

class CrawlerEngine:
    """Manages the full lifecycle of a domain crawl job"""

    # (max_workers, requests_per_second) applied instead of the job's configured
    # values when this domain was crawled recently - see _throttle_for_recrawl.
    # Ordered narrowest-window first; the first matching threshold wins.
    RECRAWL_THROTTLE_TIERS = [
        (300, 8, 5.0),     # crawled within the last 5 minutes
        (1800, 16, 12.0),  # within the last 30 minutes
        (3600, 24, 18.0),  # within the last hour
    ]

    def __init__(self, crawl_job_id: uuid.UUID):
        self.crawl_job_id = crawl_job_id
        self.job = None
        self.domain = None
        self.sitemap_parser = None
        self.rate_limiter = None
        self.issue_detector = None
        self.db_lock = asyncio.Lock()
        # Set from the job's configured value, then possibly throttled down in
        # execute() if this domain was crawled recently - see _throttle_for_recrawl.
        self.effective_max_workers = None
        # Monotonic in-memory tally of pages finished, used ONLY to pace the
        # periodic stats flush (every ~10 pages). It deliberately does NOT feed
        # the displayed total_urls_checked - that's derived from the DB in
        # _update_job_progress so it can't drift. _last_progress_sync marks the
        # tally value at the previous flush; the guard avoids "checked % 10"
        # which is unreliable under concurrency.
        self._pages_finished = 0
        self._last_progress_sync = 0
        self._progress_sync_lock = asyncio.Lock()
        # Cached after first lookup so link discovery doesn't take db_lock and
        # round-trip to Mongo on every single page - see _get_or_create_spider_sitemap.
        self._spider_sitemap_id = None
        # In-memory mirror of every url_hash already known for this domain, so
        # _extract_and_queue_links can skip the db_lock + Atlas round-trip
        # entirely for pages whose links are all already-known (the common
        # case once the crawl frontier stabilizes). Populated at stage start.
        self._known_url_hashes: Optional[set] = None
        # Mid-crawl rate-limit detection - see _note_response_for_backoff.
        # Pre-crawl throttling (_throttle_for_recrawl) only accounts for our
        # own request history; it does nothing if a target starts blocking us
        # mid-run for unrelated reasons, which just looked like the crawler
        # hammering a WAF at full speed until the job finished.
        self._consecutive_block_signals = 0
        self._backed_off = False
        self._backoff_lock = asyncio.Lock()
        # Set by _stage_http_checking to a closure that spawns crawl tasks
        # for link-discovered URLs immediately, instead of leaving them for
        # the 1s DB polling loop to rediscover - see _extract_and_queue_links.
        self._enqueue_discovered = None
        # Headless-browser renderer for SPA pages, created in execute() when
        # enabled. Lazy: Chromium only actually launches if a page's raw
        # HTML looks like an empty JS app shell (see _crawl_single_url).
        self.js_renderer = None

    async def log_event(self, level: str, message: str, event_type: str = None, entity_type: str = None, entity_id: str = None, details: dict = None):
        """Log event to python logger and database `crawl_logs` collection"""
        log_msg = f"[Job {self.crawl_job_id}] {message}"
        if level == "error":
            logger.error(log_msg)
        elif level == "warning":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        # Each call inserts its own independent CrawlLog document - no shared
        # state to protect, so no lock needed even though this runs from many
        # concurrent crawl tasks at once.
        try:
            log_entry = CrawlLog(
                crawl_job_id=self.crawl_job_id,
                level=level,
                message=message,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details or {}
            )
            await log_entry.insert()
        except Exception as e:
            logger.error(f"Failed to write log to DB: {e}")

    async def execute(self):
        """Execute the crawl pipeline"""
        try:
            # 1. Fetch Crawl Job and associated Domain
            self.job = await CrawlJob.get(self.crawl_job_id)

            if not self.job:
                logger.error(f"Crawl job {self.crawl_job_id} not found.")
                return

            # A cancel request may have arrived while this job was still
            # queued (status flipped to "stopping" before a worker picked it
            # up) - bail out immediately instead of starting the crawl at all.
            if self.job.status == CrawlJobStatus.STOPPING.value:
                raise CrawlCancelledError()

            self.domain = await Domain.get(self.job.domain_id)
            self.effective_max_workers, rate_limit = self._throttle_for_recrawl()

            await self._reset_domain_urls_for_recrawl()

            # Update status
            self.job.status = CrawlJobStatus.RUNNING.value
            self.job.started_at = datetime.utcnow()
            self.job.last_activity_at = datetime.utcnow()
            self.domain.status = DomainStatus.CRAWLING.value
            self.domain.first_crawl_at = self.domain.first_crawl_at or datetime.utcnow()
            await self.job.save()
            await self.domain.save()

            await self.log_event("info", f"Started crawl job for {self.domain.original_url}", event_type="crawl_started")
            if self.effective_max_workers < self.job.max_workers:
                await self.log_event(
                    "info",
                    f"This domain was crawled recently - throttling to {self.effective_max_workers} workers "
                    f"/ {rate_limit} req/s (configured: {self.job.max_workers} workers) to avoid tripping rate limits.",
                    event_type="recrawl_throttled"
                )

            # Setup tools. Keep-alive pool sized to the worker count - with
            # only 5 keep-alive slots (the httpx default), 32 concurrent
            # workers meant most requests re-did the full TCP+TLS handshake,
            # often costing more than the request itself.
            limits = httpx.Limits(
                max_keepalive_connections=self.effective_max_workers,
                max_connections=self.effective_max_workers,
            )
            timeout = httpx.Timeout(self.job.timeout_seconds)

            async with httpx.AsyncClient(
                limits=limits,
                timeout=timeout,
                follow_redirects=self.job.follow_redirects,
                headers=DEFAULT_REQUEST_HEADERS,
            ) as client:
                self.sitemap_parser = SitemapParser(client, self.domain.domain, timeout=self.job.timeout_seconds)
                self.rate_limiter = RateLimiter(requests_per_second=rate_limit)
                self.issue_detector = IssueDetector()
                if settings.JS_RENDERING_ENABLED:
                    self.js_renderer = JsRenderer(
                        max_pages=settings.JS_RENDER_MAX_PAGES,
                        timeout_ms=settings.JS_RENDER_TIMEOUT_MS,
                    )

                # Stage 1: Domain Validation
                await self._stage_domain_validation()
                await self._check_cancelled()

                # Stage 2: Sitemap Discovery
                await self._stage_sitemap_discovery()
                await self._check_cancelled()

                # Stage 3: HTTP Checking / Crawling URLs
                await self._stage_http_checking(client)
                await self._check_cancelled()

                # Stage 4: Duplication and Reporting
                await self._stage_reporting()

            # Snapshot this run's results before marking complete, so a later
            # crawl of the same domain (which overwrites these URL documents
            # in place) can't erase the ability to compare against this run.
            await self._snapshot_urls_for_comparison()

            # Mark Job as complete
            self.job.status = CrawlJobStatus.COMPLETED.value
            self.job.completed_at = datetime.utcnow()
            self.domain.status = DomainStatus.COMPLETED.value
            self.domain.last_crawl_at = datetime.utcnow()
            await self.job.save()
            await self.domain.save()

            await self.log_event("info", f"Successfully completed crawl job for {self.domain.original_url}", event_type="crawl_completed")

        except CrawlCancelledError:
            logger.info(f"Crawl job {self.crawl_job_id} was cancelled.")
            if self.job:
                self.job.status = CrawlJobStatus.CANCELLED.value
                self.job.completed_at = datetime.utcnow()
                await self.job.save()
            if self.domain:
                self.domain.status = DomainStatus.PAUSED.value
                await self.domain.save()
            await self.log_event("warning", "Crawl job was cancelled by the user", event_type="crawl_cancelled")

        except Exception as e:
            logger.exception(f"Unhandled exception during crawl execution: {e}")
            if self.job:
                self.job.status = CrawlJobStatus.FAILED.value
                self.job.completed_at = datetime.utcnow()
                await self.job.save()
            if self.domain:
                self.domain.status = DomainStatus.FAILED.value
                await self.domain.save()
            await self.log_event("error", f"Crawl failed: {str(e)}", event_type="crawl_failed", details={"error": str(e)})

        finally:
            if self.js_renderer:
                await self.js_renderer.close()

    def _throttle_for_recrawl(self) -> tuple:
        """Scale down concurrency/rate if this domain was crawled recently.

        Hitting the same target repeatedly in a short window (e.g. re-testing,
        or re-crawling right after a previous run) is what trips target-side
        WAF rate limits and turns into a wave of 403/429s. Reading
        domain.last_crawl_at here (before this run overwrites it on
        completion) lets us back off automatically instead of always crawling
        at full configured concurrency.
        """
        # 25 req/s is the full-speed default; the mid-crawl backoff detector
        # (_note_response_for_backoff) is the safety net that reins this in
        # the moment a target actually starts pushing back, which is what
        # makes a higher default safe - before that existed, 10 req/s was
        # the only protection we had.
        default_workers = self.job.max_workers
        default_rate = 25.0

        if not self.domain.last_crawl_at:
            return default_workers, default_rate

        elapsed = (datetime.utcnow() - self.domain.last_crawl_at).total_seconds()
        for window_seconds, throttled_workers, throttled_rate in self.RECRAWL_THROTTLE_TIERS:
            if elapsed < window_seconds:
                return min(default_workers, throttled_workers), throttled_rate

        return default_workers, default_rate

    async def _reset_domain_urls_for_recrawl(self):
        """Reset every previously-known URL for this domain back to pending.

        A fresh "Start Audit" should always do a full re-audit, not just
        whatever the sitemap happens to redeclare. Sitemap-declared URLs get
        reset again individually during sitemap parsing (that's fine, it's a
        no-op there) - this specifically covers domains with no real sitemap,
        where pages are only ever discovered by following links: without
        this, a second crawl of the same domain only ever re-checked the
        single fallback seed URL, since every other page it had already
        discovered was sitting at crawl_status="checked" and never got
        re-queued.
        """
        result = await URL.find(URL.domain_id == self.domain.id).update(
            {"$set": {
                "crawl_status": URLCrawlStatus.PENDING.value,
                "status_code": None,
                "status_category": None,
                "response_time_ms": None,
                "content_type": None,
                "content_length": None,
                "error_details": None,
            }}
        )

        # Every URL just re-queued WILL be re-checked this run, so it belongs
        # in total_urls_found from the start. Without this, a re-crawl of a
        # sitemap-less domain kept the fallback seed's count (1) while
        # "checked" climbed into the hundreds of link-discovered pages,
        # rendering as "1195 of 1 URLs checked" in the UI.
        reset_count = getattr(result, "matched_count", 0) or 0
        if reset_count:
            self.job.total_urls_found = max(self.job.total_urls_found, reset_count)

    # Status codes treated as "this target is pushing back on us", not a
    # normal client/server error - 403/429 are the obvious ones; 202 is here
    # because we've seen at least one real WAF (otterly.ai) hand back 202 with
    # no real content as its challenge/holding response instead of a 403.
    BLOCK_SIGNAL_STATUSES = {202, 403, 429}
    BLOCK_SIGNAL_THRESHOLD = 5

    async def _note_response_for_backoff(self, status_code: int):
        """Detect a target starting to rate-limit us mid-crawl and slow down.

        _throttle_for_recrawl only accounts for our own request history
        against this domain - it does nothing if the target blocks us for
        unrelated reasons (shared IP, unusual traffic pattern, etc), in which
        case the crawler would otherwise keep hammering it at full speed for
        the rest of the job. This tracks consecutive block-like responses
        across all concurrent tasks and permanently drops the request rate
        once, the first time it sees a real run of them.
        """
        async with self._backoff_lock:
            if status_code in self.BLOCK_SIGNAL_STATUSES:
                self._consecutive_block_signals += 1
            else:
                self._consecutive_block_signals = 0

            if self._backed_off or self._consecutive_block_signals < self.BLOCK_SIGNAL_THRESHOLD:
                return

            self._backed_off = True
            new_rate = max(1.0, self.rate_limiter.requests_per_second / 4)

        self.rate_limiter.update_rate(new_rate)
        await self.log_event(
            "warning",
            f"{self.domain.domain} has returned {self.BLOCK_SIGNAL_THRESHOLD} rate-limit-like responses "
            f"(403/429/202) in a row - slowing down to {new_rate} req/s for the rest of this crawl.",
            event_type="mid_crawl_backoff"
        )

    async def _check_cancelled(self):
        """Raise CrawlCancelledError if the user has asked this job to stop.

        Reads status fresh from Mongo rather than self.job.status, since the
        cancel API endpoint flips it from a different process/request while
        this engine is mid-run. Call this between stages and inside any
        long-running loop (see _stage_http_checking) so a cancel request is
        noticed within a few seconds instead of only after the whole crawl
        finishes on its own.
        """
        current = await CrawlJob.get(self.job.id)
        if current and current.status == CrawlJobStatus.STOPPING.value:
            raise CrawlCancelledError()

    async def _stage_domain_validation(self):
        """DNS resolution, SSL verification and initial HTTP head check"""
        self.job.stage_domain_validation = True
        await self.job.save()
        await self.log_event("info", "Starting Domain Validation stage", event_type="stage_domain_validation_started")

        # 1. DNS Resolution
        self.job.stage_dns_resolution = True
        await self.job.save()
        hostname = self.domain.domain
        try:
            ip_address = socket.gethostbyname(hostname)
            self.domain.ip_address = ip_address
            await self.log_event("info", f"DNS resolved for {hostname}: {ip_address}", event_type="dns_resolved", entity_type="domain", entity_id=str(self.domain.id))
        except socket.gaierror as e:
            self.domain.status = DomainStatus.FAILED.value
            await self.domain.save()
            await self.log_event("error", f"DNS resolution failed for {hostname}: {e}", event_type="dns_failed", entity_type="domain", entity_id=str(self.domain.id))
            raise Exception(f"DNS Resolution failed for host {hostname}")

        # 2. SSL Verification
        self.job.stage_ssl_verification = True
        await self.job.save()

        ssl_valid = False
        ssl_expires_at = None

        if self.domain.original_url.startswith("https://"):
            try:
                ssl_context = ssl.create_default_context()
                conn = socket.create_connection((hostname, 443), timeout=10)
                with ssl_context.wrap_socket(conn, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    expire_str = cert['notAfter']
                    ssl_expires_at = datetime.strptime(expire_str, '%b %d %H:%M:%S %Y %Z').replace(tzinfo=None)
                    ssl_valid = (ssl_expires_at > datetime.utcnow())

                self.domain.ssl_valid = ssl_valid
                self.domain.ssl_expires_at = ssl_expires_at
                await self.log_event("info", f"SSL certificate verified. Valid: {ssl_valid}, Expires: {ssl_expires_at}", event_type="ssl_verified", entity_type="domain", entity_id=str(self.domain.id))
            except Exception as e:
                self.domain.ssl_valid = False
                await self.log_event("warning", f"SSL certificate verification failed: {e}", event_type="ssl_failed", entity_type="domain", entity_id=str(self.domain.id))

        # Check Server Header via HEAD request
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=DEFAULT_REQUEST_HEADERS) as client:
                res = await client.head(self.domain.original_url)
                server = res.headers.get("server")
                if server:
                    self.domain.server_header = server
                    await self.log_event("info", f"Web server detected: {server}", event_type="server_detected")
        except Exception as e:
            logger.warning(f"HEAD request to check server header failed: {e}")

        # 3. Robots.txt
        self.job.stage_robots_found = True
        await self.job.save()

        robots_url = f"{self.domain.original_url.rstrip('/')}/robots.txt"
        self.domain.robots_txt_url = robots_url
        self.domain.robots_txt_fetched_at = datetime.utcnow()

        try:
            async with httpx.AsyncClient(timeout=10, headers=DEFAULT_REQUEST_HEADERS) as client:
                res = await client.get(robots_url)
                if res.status_code == 200:
                    self.domain.robots_txt_content = res.text
                    await self.log_event("info", "robots.txt fetched successfully", event_type="robots_txt_found", details={"size": len(res.text)})
                else:
                    self.domain.robots_txt_content = ""
                    await self.log_event("info", f"No robots.txt found (status {res.status_code})", event_type="robots_txt_not_found")
        except Exception as e:
            self.domain.robots_txt_content = ""
            await self.log_event("warning", f"Could not fetch robots.txt: {e}", event_type="robots_txt_error")

        await self.domain.save()

    async def _stage_sitemap_discovery(self):
        """Discover and parse sitemaps"""
        self.job.stage_sitemap_discovery = True
        await self.job.save()
        await self.log_event("info", "Starting Sitemap Discovery stage", event_type="stage_sitemap_discovery_started")

        # Insert Sitemaps and URLs stage flags
        self.job.stage_parsing_indexes = True
        self.job.stage_parsing_sitemaps = True
        self.job.stage_url_discovery = True
        await self.job.save()

        # Keep track of created subdomains (by normalized domain / netloc)
        subdomains_cache = {}
        sitemap_mapping = {}  # sitemap_url -> Sitemap id
        added_urls = set()
        total_urls = 0
        total_sitemaps = 0

        async def handle_sitemap_parsed(sitemap_url: str, sdata: dict):
            nonlocal total_urls, total_sitemaps
            async with self.db_lock:
                # 1. Get or create Subdomain
                parsed_sitemap_url = urlparse(sitemap_url)
                sitemap_subdomain = parsed_sitemap_url.netloc
                sub_id = None
                
                if sitemap_subdomain != self.domain.domain:
                    if sitemap_subdomain not in subdomains_cache:
                        sub = await Subdomain.find_one(
                            Subdomain.domain_id == self.domain.id,
                            Subdomain.subdomain == sitemap_subdomain
                        )
                        if not sub:
                            sub = Subdomain(
                                domain_id=self.domain.id,
                                subdomain=sitemap_subdomain,
                                normalized_url=f"{parsed_sitemap_url.scheme}://{parsed_sitemap_url.netloc}"
                            )
                            await sub.insert()
                            self.domain.total_subdomains += 1
                        subdomains_cache[sitemap_subdomain] = sub.id
                    sub_id = subdomains_cache[sitemap_subdomain]

                # 2. Check if this sitemap record is already created
                if sitemap_url in sitemap_mapping:
                    return

                parent_url = sdata.get('parent_sitemap_url')
                parent_sitemap_id = sitemap_mapping.get(parent_url) if parent_url else None

                smap = await Sitemap.find_one(
                    Sitemap.domain_id == self.domain.id,
                    Sitemap.sitemap_url == sitemap_url
                )

                if not smap:
                    smap = Sitemap(
                        domain_id=self.domain.id,
                        subdomain_id=sub_id,
                        sitemap_url=sitemap_url,
                        is_index=sdata.get('is_index', False),
                        parent_sitemap_id=parent_sitemap_id,
                        discovered_from=SitemapDiscoverySource.ROBOTS_TXT.value if parent_url is None else SitemapDiscoverySource.RECURSIVE_DISCOVERY.value,
                        status=sdata.get('status', 'pending'),
                        url_count=len(sdata.get('urls', [])),
                        response_code=sdata.get('response_code'),
                        fetched_at=datetime.utcnow(),
                        parsed_at=datetime.utcnow()
                    )
                    await smap.insert()
                else:
                    smap.subdomain_id = sub_id
                    smap.is_index = sdata.get('is_index', False)
                    smap.parent_sitemap_id = parent_sitemap_id
                    smap.status = sdata.get('status', 'pending')
                    smap.url_count = len(sdata.get('urls', []))
                    smap.response_code = sdata.get('response_code')
                    smap.fetched_at = datetime.utcnow()
                    smap.parsed_at = datetime.utcnow()
                    await smap.save()

                sitemap_mapping[sitemap_url] = smap.id
                total_sitemaps += 1
                self.job.total_sitemaps_found = total_sitemaps
                self.domain.total_sitemaps = total_sitemaps

                # 3. Add URLs for this sitemap to the database
                for url_entry in sdata.get('urls', []):
                    url_str = url_entry['url']
                    url_clean_hash = get_url_hash(url_str)
                    
                    if url_clean_hash in added_urls:
                        continue
                    added_urls.add(url_clean_hash)

                    # Get Subdomain for URL
                    parsed_url = urlparse(url_str)
                    url_subdomain = parsed_url.netloc
                    url_sub_id = None
                    if url_subdomain != self.domain.domain:
                        if url_subdomain not in subdomains_cache:
                            sub = await Subdomain.find_one(
                                Subdomain.domain_id == self.domain.id,
                                Subdomain.subdomain == url_subdomain
                            )
                            if not sub:
                                sub = Subdomain(
                                    domain_id=self.domain.id,
                                    subdomain=url_subdomain,
                                    normalized_url=f"{parsed_url.scheme}://{parsed_url.netloc}"
                                )
                                await sub.insert()
                                self.domain.total_subdomains += 1
                            subdomains_cache[url_subdomain] = sub.id
                        url_sub_id = subdomains_cache[url_subdomain]

                    # Parse Priority & Dates
                    priority = url_entry.get('priority')
                    lastmod_date = None
                    if url_entry.get('lastmod'):
                        try:
                            lastmod_date = datetime.strptime(url_entry['lastmod'][:10], '%Y-%m-%d').date()
                        except:
                            pass

                    # Match on url_hash alone: the collection's unique index is
                    # on url_hash (which already encodes the full URL incl.
                    # host), NOT on (domain_id, url_hash). Scoping this lookup
                    # to domain_id could miss a row that exists under a
                    # duplicate domain record (e.g. "https://Ahrefs.com" vs
                    # "https://ahrefs.com"), and then the insert below would
                    # crash the entire crawl with an E11000 duplicate-key
                    # error - exactly what killed the sitemap-less fallback
                    # path on re-crawls.
                    url_obj = await URL.find_one(URL.url_hash == url_clean_hash)

                    if not url_obj:
                        url_obj = URL(
                            domain_id=self.domain.id,
                            subdomain_id=url_sub_id,
                            sitemap_id=smap.id,
                            url=url_str,
                            url_hash=url_clean_hash,
                            sitemap_last_modified=lastmod_date,
                            sitemap_change_frequency=url_entry.get('changefreq'),
                            sitemap_priority=priority,
                            crawl_status=URLCrawlStatus.PENDING.value
                        )
                        try:
                            await url_obj.insert()
                        except Exception:
                            # Lost a race (another task inserted the same hash)
                            # or a stale index read - re-fetch and update
                            # instead of failing the whole crawl.
                            existing = await URL.find_one(URL.url_hash == url_clean_hash)
                            if existing is None:
                                raise
                            url_obj = existing
                            url_obj.domain_id = self.domain.id
                            url_obj.subdomain_id = url_sub_id
                            url_obj.sitemap_id = smap.id
                            url_obj.crawl_status = URLCrawlStatus.PENDING.value
                            await url_obj.save()
                    else:
                        url_obj.domain_id = self.domain.id
                        url_obj.subdomain_id = url_sub_id
                        url_obj.sitemap_id = smap.id
                        url_obj.sitemap_last_modified = lastmod_date
                        url_obj.sitemap_change_frequency = url_entry.get('changefreq')
                        url_obj.sitemap_priority = priority
                        url_obj.crawl_status = URLCrawlStatus.PENDING.value
                        url_obj.status_code = None
                        url_obj.status_category = None
                        url_obj.response_time_ms = None
                        url_obj.content_type = None
                        url_obj.content_length = None
                        url_obj.canonical_url = None
                        url_obj.robots_meta = None
                        url_obj.is_indexable = None
                        url_obj.meta_data = {}
                        url_obj.seo_issues = []
                        url_obj.error_details = None
                        url_obj.crawl_attempt = 0
                        await url_obj.save()

                    total_urls += 1

                # Never shrink below the re-crawl reset count: on a re-crawl
                # every previously-known URL is re-checked regardless of
                # whether the sitemap still declares it (see
                # _reset_domain_urls_for_recrawl).
                self.job.total_urls_found = max(total_urls, self.job.total_urls_found)
                self.domain.total_urls = max(total_urls, self.domain.total_urls or 0)
                self.job.last_activity_at = datetime.utcnow()
                await self.job.save()
                await self.domain.save()
                
                logger.info(f"Discovered sitemap {sitemap_url}: {len(sdata.get('urls', []))} URLs (total URLs found: {total_urls})")

        # Discover sitemaps (using callback)
        await self.sitemap_parser.discover_sitemaps(self.domain.original_url, on_sitemap_parsed=handle_sitemap_parsed)

        # Fall back to crawling at least the homepage if no usable URLs were
        # found - this can happen even when sitemap *records* got created
        # (e.g. every guessed sitemap path 301s to a generic homepage instead
        # of returning real XML), so check total_urls rather than sitemap_mapping.
        if total_urls == 0:
            await self.log_event("info", "No usable sitemap URLs found. Creating a default fallback sitemap", event_type="sitemap_fallback")
            fallback_sitemap_url = f"{self.domain.original_url.rstrip('/')}/sitemap_fallback.xml"
            fallback_data = {
                'urls': [{'url': self.domain.original_url, 'lastmod': None, 'changefreq': None, 'priority': 1.0}],
                'is_index': False,
                'parent_sitemap_url': None,
                'response_code': 200,
                'status': 'generated'
            }
            await handle_sitemap_parsed(fallback_sitemap_url, fallback_data)

        await self.log_event("info", f"Discovered {total_sitemaps} sitemaps and {total_urls} URLs", event_type="sitemaps_discovered", details={"sitemaps_count": total_sitemaps, "urls_count": total_urls})
        await self.log_event("info", f"Queued {total_urls} URLs for HTTP checking", event_type="urls_queued", details={"urls_count": total_urls})

    async def _stage_http_checking(self, client: httpx.AsyncClient):
        """Asynchronously crawl URLs dynamically using a polling queue with concurrency limit"""
        self.job.stage_http_checking = True
        await self.job.save()

        await self.log_event("info", "Starting HTTP Checking stage", event_type="stage_http_checking_started")

        # Get initial list of pending URLs (plain read, no shared state involved)
        urls = await URL.find(
            URL.domain_id == self.domain.id,
            URL.crawl_status == URLCrawlStatus.PENDING.value
        ).to_list(None)

        # One-time seed of the known-hash cache (see __init__) so link discovery
        # doesn't need a DB round-trip per page for already-known links.
        self._known_url_hashes = set(u.url_hash for u in urls)

        if not urls:
            await self.log_event("warning", "No pending URLs found for crawling.", event_type="no_urls_found")
            return

        # Keep track of active task set and overall scheduled URL strings
        active_urls = set(u.url for u in urls)
        running_tasks = set()
        sem = asyncio.Semaphore(self.effective_max_workers)

        async def crawl_and_release(url_to_crawl: URL):
            try:
                async with sem:
                    await self.rate_limiter.acquire_async()
                    await self._crawl_single_url(client, url_to_crawl)
            finally:
                running_tasks.discard(asyncio.current_task())

        # Let _extract_and_queue_links hand link-discovered URLs straight to
        # this stage the moment they're inserted. Without this, every
        # discovery "wave" waited for the next 1s DB poll tick below before
        # its URLs started crawling, which put a hard floor on how fast a
        # sitemap-less site (where the entire frontier is link-discovered,
        # often through deep chains like /page/1 -> /page/2 -> ...) could go.
        def enqueue_discovered(new_docs):
            for discovered in new_docs:
                if discovered.url in active_urls:
                    continue
                active_urls.add(discovered.url)
                new_task = asyncio.create_task(crawl_and_release(discovered))
                running_tasks.add(new_task)
        self._enqueue_discovered = enqueue_discovered

        # Spawn initial tasks
        for url_obj in urls:
            task = asyncio.create_task(crawl_and_release(url_obj))
            running_tasks.add(task)

        # Main polling loop. The 1s tick is the cancellation check (cheap
        # single-doc read); the pending-URL scan is a *fallback* for anything
        # enqueue_discovered missed and runs only every 5th tick, as a
        # projection of {_id, url} rather than full documents - on a
        # several-thousand-URL site, materializing every pending document
        # once per second was tens of MB of allocation churn per second for
        # the entire crawl (a real contributor to OOM-killing the worker).
        poll_tick = 0
        while True:
            await asyncio.sleep(1.0)
            poll_tick += 1

            current = await CrawlJob.get(self.job.id)
            if current and current.status == CrawlJobStatus.STOPPING.value:
                for task in running_tasks:
                    task.cancel()
                await asyncio.gather(*running_tasks, return_exceptions=True)
                await self._update_job_progress()
                raise CrawlCancelledError()

            # Scan on every 5th tick, or immediately when all tasks have
            # drained (so completion isn't delayed and the final "anything
            # left?" check is never skipped).
            if poll_tick % 5 != 0 and running_tasks:
                continue

            pending_rows = await URL.find(
                URL.domain_id == self.domain.id,
                URL.crawl_status == URLCrawlStatus.PENDING.value
            ).aggregate([{"$project": {"_id": 1, "url": 1}}]).to_list()

            # Filter out URLs already in queue or processing; only fetch full
            # documents for the (rare) genuinely-new ones.
            unseen_ids = [r["_id"] for r in pending_rows if r.get("url") not in active_urls]
            new_urls = (
                await URL.find({"_id": {"$in": unseen_ids}}).to_list()
                if unseen_ids else []
            )

            # If no pending URLs and no active crawl tasks remain, we are completely done!
            if not new_urls and not running_tasks:
                break

            # Enqueue new tasks
            for url_obj in new_urls:
                active_urls.add(url_obj.url)
                task = asyncio.create_task(crawl_and_release(url_obj))
                running_tasks.add(task)

        # Force save final stats
        await self._update_job_progress()

    async def _crawl_single_url(self, client: httpx.AsyncClient, url_obj: URL):
        """Crawl a single URL and save result to database.

        Each concurrent task owns a distinct url_obj, so these saves don't need
        db_lock - only self.job/self.domain mutations (shared across all tasks)
        do, and only around the increment+save itself, not the whole request.
        """
        # Increment the attempt counter in memory only - it's persisted by the
        # single terminal save below (CHECKED or FAILED). The old code did a
        # full extra Atlas round-trip here just to flip the row to "checking",
        # but the polling loop already dedupes in-flight URLs via the in-memory
        # `active_urls` set, so that write bought nothing except ~33% more DB
        # traffic on the hot path (every URL: checking-save + final-save). If
        # the worker dies mid-page the row simply stays "pending" and the
        # reaper re-queues it - which is exactly what we want anyway.
        url_obj.crawl_attempt += 1

        start_time = time.time()
        logger.info(f"Crawl HTTP request started: {url_obj.url}")

        try:
            # Fetch URL, streaming the body so a single huge response (video,
            # PDF, a multi-MB page) can never pull more than
            # CRAWLER_MAX_FETCH_BYTES into memory. client.get() would buffer
            # the entire body before we could look at its size.
            body = bytearray()
            truncated = False
            async with client.stream("GET", url_obj.url, timeout=self.job.timeout_seconds) as response:
                await self._note_response_for_backoff(response.status_code)

                # Update URL details (first phase commit)
                url_obj.status_code = response.status_code
                url_obj.final_url = str(response.url)
                url_obj.content_type = response.headers.get("content-type", "").split(";")[0].strip()

                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > settings.CRAWLER_MAX_FETCH_BYTES:
                        truncated = True
                        break

                response_time_ms = int((time.time() - start_time) * 1000)
                url_obj.response_time_ms = response_time_ms
                header_length = response.headers.get("content-length")
                url_obj.content_length = int(header_length) if header_length else len(body)
                charset = response.charset_encoding or "utf-8"

                # Categorize status code
                if 200 <= response.status_code < 300:
                    url_obj.status_category = URLStatusCategory.SUCCESS.value
                elif 300 <= response.status_code < 400:
                    url_obj.status_category = URLStatusCategory.REDIRECT.value
                elif 400 <= response.status_code < 500:
                    url_obj.status_category = URLStatusCategory.CLIENT_ERROR.value
                elif response.status_code >= 500:
                    url_obj.status_category = URLStatusCategory.SERVER_ERROR.value

                # Extract redirects
                redirects = []
                if response.history:
                    redirects = [str(r.url) for r in response.history]
                url_obj.redirect_chain = redirects
                # (saved once at the end, together with the SEO/issue fields
                # below - each url_obj.save() is its own Atlas round-trip.)

            # Extract SEO data
            seo_data = None
            issues = []
            soup = None
            oversized = truncated or len(body) > settings.CRAWLER_MAX_PARSE_BYTES
            if oversized:
                # Status/headers are already recorded above - just skip the
                # HTML parse. A soup of a multi-MB page costs ~10x its size
                # in RAM, and with max_workers pages in flight at once that
                # spike is exactly what OOM-killed the worker on heavy sites.
                await self.log_event(
                    "warning",
                    f"Skipping content audit for {url_obj.url} - page is "
                    f"{len(body) // 1024}KB{'+' if truncated else ''} (limit {settings.CRAWLER_MAX_PARSE_BYTES // 1024}KB)",
                    event_type="page_too_large", entity_type="url", entity_id=str(url_obj.id),
                )
            if "text/html" in url_obj.content_type and not oversized:
                html_content = bytes(body).decode(charset, errors="replace")
                del body
                try:
                    # HTML parsing + tag walking is CPU-bound and was running
                    # inline on the event loop, blocking every other concurrent
                    # worker for its duration. Off-thread lets requests for the
                    # other max_workers tasks actually overlap with this.
                    seo_data, soup = await asyncio.to_thread(
                        SEOExtractor.extract_all, html_content, url_obj.url, self.domain.domain, response_time_ms
                    )

                    # Client-rendered app shell? Escalate to headless
                    # Chromium and re-run extraction on the rendered DOM so
                    # SPAs get audited on their real content (and their
                    # links actually get discovered) instead of an empty
                    # <div id="root">.
                    if self.js_renderer and looks_js_rendered(html_content, seo_data.get('word_count', 0)):
                        rendered_html = await self.js_renderer.render(url_obj.url)
                        if rendered_html:
                            seo_data, soup = await asyncio.to_thread(
                                SEOExtractor.extract_all, rendered_html, url_obj.url, self.domain.domain, response_time_ms
                            )
                            seo_data['js_rendered'] = True
                            await self.log_event(
                                "info",
                                f"Rendered {url_obj.url} with headless browser (client-side app detected)",
                                event_type="js_rendered", entity_type="url", entity_id=str(url_obj.id),
                            )

                    issues = self.issue_detector.detect_issues(seo_data)
                except Exception as e:
                    logger.error(f"Error parsing HTML for {url_obj.url}: {e}")

            if issues:
                # One insert_many instead of N sequential log_event() calls -
                # a page with 5 issues used to mean 5 extra serialized Atlas
                # round-trips (issues are common: most pages have several).
                log_entries = []
                for issue in issues:
                    message = f"{issue['category']} Issue ({issue['issue']}) on {url_obj.url}: {issue['details']}"
                    level = issue['type']
                    if level == "error":
                        logger.error(f"[Job {self.crawl_job_id}] {message}")
                    elif level == "warning":
                        logger.warning(f"[Job {self.crawl_job_id}] {message}")
                    else:
                        logger.info(f"[Job {self.crawl_job_id}] {message}")
                    log_entries.append(CrawlLog(
                        crawl_job_id=self.crawl_job_id,
                        level=level,
                        message=message,
                        event_type="seo_issue_detected",
                        entity_type="url",
                        entity_id=str(url_obj.id),
                        details=issue
                    ))
                try:
                    await CrawlLog.insert_many(log_entries)
                except Exception as e:
                    logger.error(f"Failed to write issue logs to DB: {e}")

            # Finalize URL check (second phase commit)
            if seo_data:
                # Check indexability
                robots = seo_data.get('robots', '').lower()
                url_obj.is_indexable = 'noindex' not in robots
                url_obj.canonical_url = seo_data.get('canonical_url')
                url_obj.robots_meta = seo_data.get('robots')
                url_obj.meta_data = seo_data

            url_obj.seo_issues = issues
            url_obj.crawl_status = URLCrawlStatus.CHECKED.value
            url_obj.last_checked_at = datetime.utcnow()
            await url_obj.save()

            # Queue discovered internal links before dropping the parse tree.
            if soup:
                await self._extract_and_queue_links(soup, url_obj.url)

            # Release everything heavy this task built. The sitemap-seeded URL
            # objects are held in the `urls` list for the entire crawl (see
            # _stage_http_checking), so anything left attached to url_obj here
            # stays resident until the whole crawl ends - full SEO metadata
            # (every link + image) for every page. On a several-thousand-page
            # site with heavy pages that accumulation alone exhausted the 1GB
            # worker around page ~1000. The DB already holds the real values;
            # these in-memory copies are dead weight.
            soup = None
            seo_data = None
            issues = None
            url_obj.meta_data = {}
            url_obj.seo_issues = []
            url_obj.redirect_chain = []

        except httpx.TimeoutException as e:
            url_obj.crawl_status = URLCrawlStatus.FAILED.value
            url_obj.status_category = URLStatusCategory.TIMEOUT.value
            url_obj.error_details = f"Timeout: {str(e)}"
            await url_obj.save()
            await self.log_event("error", f"Crawl timeout for {url_obj.url}", event_type="crawl_timeout", entity_type="url", entity_id=str(url_obj.id))

        except httpx.ConnectError as e:
            url_obj.crawl_status = URLCrawlStatus.FAILED.value
            url_obj.status_category = URLStatusCategory.DNS_ERROR.value
            url_obj.error_details = f"Connection error: {str(e)}"
            await url_obj.save()
            await self.log_event("error", f"Connection error for {url_obj.url}", event_type="crawl_connection_error", entity_type="url", entity_id=str(url_obj.id))

        except Exception as e:
            url_obj.crawl_status = URLCrawlStatus.FAILED.value
            url_obj.status_category = URLStatusCategory.NETWORK_ERROR.value
            url_obj.error_details = f"Unhandled error: {str(e)}"
            await url_obj.save()
            await self.log_event("error", f"Crawl failed for {url_obj.url}: {str(e)}", event_type="crawl_url_failed", entity_type="url", entity_id=str(url_obj.id))

        # Periodic updates to the UI / stats (roughly every 10 checked URLs).
        # Using "checked % 10 == 0" is unreliable under concurrency: with up to
        # max_workers tasks incrementing the same shared counter, the exact
        # multiple-of-10 value can get skipped entirely (another task already
        # bumped the count past it by the time this task reads it), so the
        # sync silently never fires until the crawl fully completes. Track
        # the last synced count instead and trigger on "at least 10 since".
        async with self._progress_sync_lock:
            self._pages_finished += 1
            should_sync = self._pages_finished - self._last_progress_sync >= 10
            if should_sync:
                self._last_progress_sync = self._pages_finished
        if should_sync:
            await self._update_job_progress()

    @staticmethod
    def _status_bucket_expr() -> dict:
        """Mongo $switch expression bucketing a URL doc into a stat category.

        Mirrors the old Python elif chain: error categories first (they have
        no status_code), then status-code ranges.
        """
        def _cat_eq(cat):
            return {"$eq": ["$status_category", cat]}

        def _code_range(lo, hi=None):
            conds = [{"$ne": ["$status_code", None]}, {"$gte": ["$status_code", lo]}]
            if hi is not None:
                conds.append({"$lt": ["$status_code", hi]})
            return {"$and": conds}

        return {
            "$switch": {
                "branches": [
                    {"case": _cat_eq(URLStatusCategory.TIMEOUT.value), "then": "timeout"},
                    {"case": _cat_eq(URLStatusCategory.DNS_ERROR.value), "then": "dns"},
                    {"case": _cat_eq(URLStatusCategory.SSL_ERROR.value), "then": "ssl"},
                    {"case": _code_range(200, 300), "then": "2xx"},
                    {"case": _code_range(300, 400), "then": "3xx"},
                    {"case": _code_range(400, 500), "then": "4xx"},
                    {"case": _code_range(500), "then": "5xx"},
                ],
                "default": "other",
            }
        }

    async def _update_job_progress(self):
        """Recalculate and update database stats on the CrawlJob"""
        async with self.db_lock:
            # Compute stats server-side with one aggregation instead of
            # shipping every checked URL document over the wire: this runs
            # every ~10 pages, so on large crawls the old fetch-everything
            # version transferred O(n^2) total data across the run - and it
            # did so while holding db_lock, stalling every worker's counter
            # increment for the duration of an ever-growing Atlas read.
            #
            # The match must stay scoped to updated_at >= job.started_at:
            # URLs are stored per-domain and reused across crawl runs, so an
            # unscoped count would pull in status-code counts left over from
            # previous jobs of the same domain.
            rows = await URL.find(
                URL.domain_id == self.domain.id,
                {"crawl_status": {"$in": [URLCrawlStatus.CHECKED.value, URLCrawlStatus.FAILED.value]}},
                URL.updated_at >= self.job.started_at
            ).aggregate([
                {"$group": {
                    "_id": self._status_bucket_expr(),
                    "count": {"$sum": 1},
                    "avg_rt": {"$avg": "$response_time_ms"},
                    "rt_count": {"$sum": {"$cond": [{"$ne": ["$response_time_ms", None]}, 1, 0]}},
                }}
            ]).to_list()

            if not rows:
                return

            buckets = {r["_id"]: r for r in rows}

            def count_of(bucket):
                return buckets.get(bucket, {}).get("count", 0)

            total_checked = sum(r["count"] for r in rows)
            weighted_rt = sum((r["avg_rt"] or 0) * r["rt_count"] for r in rows)
            total_rt_count = sum(r["rt_count"] for r in rows)
            avg_resp_time = int(weighted_rt / total_rt_count) if total_rt_count else None

            self.job.avg_response_time_ms = avg_resp_time
            self.job.urls_2xx = count_of("2xx")
            self.job.urls_3xx = count_of("3xx")
            self.job.urls_4xx = count_of("4xx")
            self.job.urls_5xx = count_of("5xx")
            self.job.urls_timeout = count_of("timeout")
            self.job.urls_dns_error = count_of("dns")
            self.job.urls_ssl_error = count_of("ssl")

            # Derive total_urls_checked from the database, NOT the in-memory
            # per-page counter. That counter drifts under concurrency (a
            # completed 183-URL crawl was persisting values like 24/132),
            # leaving the progress bar stuck below 100% and disagreeing with
            # the status distribution - which is computed from this very same
            # aggregation, so the two now always reconcile by construction.
            self.job.total_urls_checked = total_checked
            self.domain.crawled_urls = total_checked

            # Calculate speed
            elapsed_sec = (datetime.utcnow() - self.job.started_at).total_seconds()
            if elapsed_sec > 0:
                self.job.crawl_speed_urls_per_sec = round(total_checked / elapsed_sec, 2)

            self.job.last_activity_at = datetime.utcnow()
            await self.job.save()
            await self.domain.save()

    async def _stage_reporting(self):
        """Detect duplication, generate issues reports and populate statistics tables"""
        await self.log_event("info", "Starting Duplication check & Reporting stage", event_type="stage_reporting_started")

        # 1. Fetch checked HTML URLs for duplication checks - scoped to this
        # job's run for the same reason as _update_job_progress above.
        #
        # Project each doc down to only the fields the whole reporting stage
        # actually uses. Loading full documents here meant pulling every
        # page's complete SEO metadata (all links + images) into memory at
        # once - on a several-thousand-page site that end-of-crawl spike was
        # its own OOM even after the per-page accumulation fix. meta_data is
        # slimmed to just the four fields duplication detection reads.
        from types import SimpleNamespace
        rows = await URL.find(
            URL.domain_id == self.domain.id,
            URL.crawl_status == URLCrawlStatus.CHECKED.value,
            URL.updated_at >= self.job.started_at
        ).aggregate([
            {"$project": {
                "url": 1,
                "status_code": 1,
                "status_category": 1,
                "response_time_ms": 1,
                "content_type": 1,
                "content_length": 1,
                "subdomain_id": 1,
                "m_title": "$meta_data.title",
                "m_desc": "$meta_data.meta_description",
                "m_h1": "$meta_data.h1",
                "m_wc": "$meta_data.word_count",
            }},
        ]).to_list()

        def _row_id(v):
            if isinstance(v, uuid.UUID):
                return v
            try:
                return uuid.UUID(bytes=bytes(v))
            except (TypeError, ValueError):
                return v

        checked_urls = [
            SimpleNamespace(
                id=_row_id(r["_id"]),
                url=r.get("url"),
                status_code=r.get("status_code"),
                status_category=r.get("status_category"),
                response_time_ms=r.get("response_time_ms"),
                content_type=r.get("content_type"),
                content_length=r.get("content_length"),
                subdomain_id=r.get("subdomain_id"),
                meta_data={
                    "title": r.get("m_title"),
                    "meta_description": r.get("m_desc"),
                    "h1": r.get("m_h1"),
                    "word_count": r.get("m_wc"),
                },
            )
            for r in rows
        ]

        html_results = []
        for url_obj in checked_urls:
            if url_obj.meta_data and isinstance(url_obj.meta_data, dict):
                # Ensure the url is present in the dictionary
                meta = url_obj.meta_data.copy()
                meta['url'] = url_obj.url
                meta['status_code'] = url_obj.status_code
                meta['size'] = url_obj.content_length
                html_results.append(meta)

        # Duplication check
        if len(html_results) > 1:
            await self.log_event("info", f"Running duplication checks on {len(html_results)} pages...", event_type="duplication_check_started")
            # Off-thread: even with its pre-filters this is O(n^2) pure-CPU
            # work, and running it inline froze the event loop (cancellation
            # checks, progress polls) for the whole comparison on big sites.
            dup_issues = await asyncio.to_thread(
                self.issue_detector.detect_duplication_issues, html_results
            )
            for issue in dup_issues:
                # Find matching url object
                target_url_obj = next((u for u in checked_urls if u.url == issue['url']), None)
                entity_id = str(target_url_obj.id) if target_url_obj else None
                await self.log_event(
                    level=issue['type'],
                    message=f"Duplication Issue on {issue['url']}: {issue['details']}",
                    event_type="seo_issue_detected",
                    entity_type="url",
                    entity_id=entity_id,
                    details=issue
                )

        # 2. Consolidate and insert Reports Grouped by issue type
        all_detected_issues = self.issue_detector.get_issues()
        grouped_issues = {}  # category -> list of issue dicts
        for issue in all_detected_issues:
            cat = issue.get('category', 'General')
            if cat not in grouped_issues:
                grouped_issues[cat] = []
            grouped_issues[cat].append(issue)

        for cat, list_of_issues in grouped_issues.items():
            # Create a report record
            report = Report(
                domain_id=self.domain.id,
                crawl_job_id=self.crawl_job_id,
                report_type=cat.lower().replace(' ', '_'),
                title=f"{cat} Issues Report",
                description=f"Automated review listing all {cat} issues detected during crawl.",
                data={"issues": list_of_issues},
                issues_count=len(list_of_issues)
            )
            await report.insert()

        # 3. Create or Update CrawlStatistics
        stats = await CrawlStatistics.find_one(CrawlStatistics.domain_id == self.domain.id)

        if not stats:
            stats = CrawlStatistics(domain_id=self.domain.id)
            await stats.insert()

        stats.crawl_job_id = self.crawl_job_id
        stats.total_urls = self.job.total_urls_found
        stats.successful_urls = self.job.urls_2xx
        stats.redirects = self.job.urls_3xx
        stats.client_errors_4xx = self.job.urls_4xx
        stats.server_errors_5xx = self.job.urls_5xx
        stats.timeouts = self.job.urls_timeout
        stats.dns_errors = self.job.urls_dns_error
        stats.ssl_errors = self.job.urls_ssl_error
        stats.network_errors = len([u for u in checked_urls if u.status_category == URLStatusCategory.NETWORK_ERROR.value])

        # Performance
        stats.avg_response_time_ms = self.job.avg_response_time_ms
        resp_times = [u.response_time_ms for u in checked_urls if u.response_time_ms is not None]
        if resp_times:
            stats.min_response_time_ms = min(resp_times)
            stats.max_response_time_ms = max(resp_times)
            # Calculate percentiles
            sorted_times = sorted(resp_times)
            n = len(sorted_times)
            stats.p95_response_time_ms = sorted_times[int(n * 0.95)] if n > 0 else None
            stats.p99_response_time_ms = sorted_times[int(n * 0.99)] if n > 0 else None

        # Content Types count
        c_types = {
            'html': 0, 'css': 0, 'js': 0, 'json': 0, 'xml': 0, 'image': 0, 'pdf': 0, 'video': 0, 'other': 0
        }
        for u in checked_urls:
            c_type = (u.content_type or "").lower()
            if "html" in c_type:
                c_types['html'] += 1
            elif "css" in c_type:
                c_types['css'] += 1
            elif "javascript" in c_type or "js" in c_type:
                c_types['js'] += 1
            elif "json" in c_type:
                c_types['json'] += 1
            elif "xml" in c_type:
                c_types['xml'] += 1
            elif "image" in c_type:
                c_types['image'] += 1
            elif "pdf" in c_type:
                c_types['pdf'] += 1
            elif "video" in c_type or "mp4" in c_type:
                c_types['video'] += 1
            else:
                c_types['other'] += 1

        stats.html_urls = c_types['html']
        stats.css_urls = c_types['css']
        stats.js_urls = c_types['js']
        stats.json_urls = c_types['json']
        stats.xml_urls = c_types['xml']
        stats.image_urls = c_types['image']
        stats.pdf_urls = c_types['pdf']
        stats.video_urls = c_types['video']
        stats.other_urls = c_types['other']

        # Health score calculation: simple formula starting at 100
        # deduct 5 points per error, 1 point per warning
        health = 100
        broken_links_count = 0
        for issue in all_detected_issues:
            severity = issue.get('type')
            if severity == 'error':
                health -= 5
                if 'broken' in issue.get('issue', '').lower() or 'client error' in issue.get('issue', '').lower():
                    broken_links_count += 1
            elif severity == 'warning':
                health -= 1
        stats.health_score = max(0, health)
        stats.broken_links_count = broken_links_count
        
        # Subdomains health update
        for sub_id in set([u.subdomain_id for u in checked_urls if u.subdomain_id is not None]):
            # Find issues related to this subdomain URLs
            sub_urls = await URL.find(URL.subdomain_id == sub_id).to_list(None)
            sub_url_strings = set(u.url for u in sub_urls)

            sub_health = 100
            for issue in all_detected_issues:
                if issue.get('url') in sub_url_strings:
                    if issue.get('type') == 'error':
                        sub_health -= 5
                    elif issue.get('type') == 'warning':
                        sub_health -= 1

            sub_health = max(0, sub_health)
            subdomain = await Subdomain.get(sub_id)
            if subdomain:
                subdomain.health_score = sub_health
                subdomain.crawled_at = datetime.utcnow()
                subdomain.status = "crawled"
                await subdomain.save()

        # Timings
        stats.crawl_start_time = self.job.started_at
        stats.crawl_end_time = datetime.utcnow()
        stats.crawl_duration_minutes = int((stats.crawl_end_time - stats.crawl_start_time).total_seconds() / 60)

        await stats.save()
        await self.log_event("info", f"Reporting completed. Health Score: {stats.health_score}", event_type="reporting_completed", details={"health_score": stats.health_score})

    async def _snapshot_urls_for_comparison(self):
        """Freeze this job's checked URLs into UrlSnapshot so a later crawl of
        the same domain (which overwrites these URL documents in place) can't
        take away the ability to compare this run against a future one.
        """
        checked_urls = await URL.find(
            URL.domain_id == self.domain.id,
            URL.updated_at >= self.job.started_at,
        ).to_list(None)

        if not checked_urls:
            return

        snapshots = [
            UrlSnapshot(
                crawl_job_id=self.crawl_job_id,
                domain_id=self.domain.id,
                url=u.url,
                url_hash=u.url_hash,
                status_code=u.status_code,
                status_category=u.status_category,
                response_time_ms=u.response_time_ms,
                is_indexable=u.is_indexable,
                seo_issues=u.seo_issues,
            )
            for u in checked_urls
        ]
        await UrlSnapshot.insert_many(snapshots)

    async def _get_or_create_spider_sitemap(self) -> uuid.UUID:
        """Get or create a virtual sitemap entry for HTML link discovery.

        Cached on the instance after the first call - this used to hit Mongo
        (under db_lock, serializing every other concurrent worker) on every
        single crawled page, which was a major source of the crawl slowness.
        """
        if self._spider_sitemap_id is not None:
            return self._spider_sitemap_id

        spider_url = f"https://{self.domain.domain}/html-spider"

        async with self.db_lock:
            if self._spider_sitemap_id is not None:
                return self._spider_sitemap_id

            spider_sitemap = await Sitemap.find_one(
                Sitemap.domain_id == self.domain.id,
                Sitemap.sitemap_url == spider_url
            )

            if not spider_sitemap:
                spider_sitemap = Sitemap(
                    id=uuid.uuid4(),
                    domain_id=self.domain.id,
                    sitemap_url=spider_url,
                    is_index=False,
                    discovered_from="spider",
                    status="fetched",
                    url_count=0
                )
                await spider_sitemap.insert()

            self._spider_sitemap_id = spider_sitemap.id
            return self._spider_sitemap_id

    async def _extract_and_queue_links(self, soup, current_url: str):
        """Extract all internal links from soup and queue them as pending if not already existing"""
        from urllib.parse import urljoin, urlparse
        
        # Enforce max limit of 10,000 URLs to avoid infinite crawl loops
        if self.job.total_urls_found >= 10000:
            return

        links = soup.find_all('a', href=True)
        new_urls = []
        
        for link in links:
            href = link.get('href', '').strip()
            if not href or href.startswith(('#', 'mailto:', 'tel:', 'javascript:')):
                continue
                
            # Make absolute URL
            absolute_url = urljoin(current_url, href)
            parsed = urlparse(absolute_url)
            
            if parsed.scheme not in ('http', 'https'):
                continue
                
            # Clean URL (strip fragment/hash)
            clean_url = parsed._replace(fragment='').geturl()
            
            # Check domain matching (only internal links)
            url_domain_clean = parsed.netloc.replace('www.', '', 1).lower()
            base_domain_clean = self.domain.domain.replace('www.', '', 1).lower()
            
            if url_domain_clean == base_domain_clean:
                new_urls.append(clean_url)
                
        if not new_urls:
            return

        # Hash candidates and drop anything already in the in-memory known-hash
        # cache first - no lock, no DB round-trip. Once the crawl frontier
        # stabilizes (after the first page or two), nearly every page's links
        # are already known, so this skips the Atlas round-trip entirely for
        # the vast majority of pages instead of paying for it on every single one.
        candidates = {get_url_hash(url_str): url_str for url_str in new_urls}
        unknown = {h: u for h, u in candidates.items() if h not in self._known_url_hashes}
        if not unknown:
            return

        # Get spider sitemap ID
        spider_sitemap_id = await self._get_or_create_spider_sitemap()

        async with self.db_lock:
            # Recheck limit inside the lock to be safe
            if self.job.total_urls_found >= 10000:
                return

            # Re-filter against the cache under the lock in case another
            # concurrent task inserted some of these since the check above.
            unknown = {h: u for h, u in unknown.items() if h not in self._known_url_hashes}
            if not unknown:
                return

            existing_docs = await URL.find(
                URL.domain_id == self.domain.id,
                {"url_hash": {"$in": list(unknown.keys())}}
            ).to_list()
            existing_hashes = {u.url_hash for u in existing_docs}
            self._known_url_hashes.update(existing_hashes)

            remaining_capacity = 10000 - self.job.total_urls_found
            new_docs = [
                URL(
                    id=uuid.uuid4(),
                    domain_id=self.domain.id,
                    sitemap_id=spider_sitemap_id,
                    url=url_str,
                    url_hash=url_hash,
                    crawl_status=URLCrawlStatus.PENDING.value,
                    meta_data={}
                )
                for url_hash, url_str in unknown.items()
                if url_hash not in existing_hashes
            ][:remaining_capacity]

            if new_docs:
                await URL.insert_many(new_docs)
                self._known_url_hashes.update(d.url_hash for d in new_docs)
                self.job.total_urls_found += len(new_docs)
                await self.job.save()
                # Start crawling them right away rather than waiting for the
                # polling loop's next tick to find them (it still acts as the
                # fallback if this closure isn't wired up, e.g. in tests).
                if self._enqueue_discovered:
                    self._enqueue_discovered(new_docs)
