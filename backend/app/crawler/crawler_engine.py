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
from app.crawler.rate_limiter import RateLimiter
from app.crawler.seo_extractor import SEOExtractor
from app.crawler.sitemap_parser import SitemapParser
from app.crawler.issue_detector import IssueDetector

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

class CrawlerEngine:
    """Manages the full lifecycle of a domain crawl job"""

    def __init__(self, crawl_job_id: uuid.UUID):
        self.crawl_job_id = crawl_job_id
        self.job = None
        self.domain = None
        self.sitemap_parser = None
        self.rate_limiter = None
        self.issue_detector = None
        self.db_lock = asyncio.Lock()

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

            self.domain = await Domain.get(self.job.domain_id)

            # Reset stuck URLs from previous interrupted runs
            stuck_urls = await URL.find(
                URL.domain_id == self.domain.id,
                URL.crawl_status == URLCrawlStatus.CHECKING.value
            ).to_list(None)
            for url_obj in stuck_urls:
                url_obj.crawl_status = URLCrawlStatus.PENDING.value
                await url_obj.save()

            # Update status
            self.job.status = CrawlJobStatus.RUNNING.value
            self.job.started_at = datetime.utcnow()
            self.domain.status = DomainStatus.CRAWLING.value
            self.domain.first_crawl_at = self.domain.first_crawl_at or datetime.utcnow()
            await self.job.save()
            await self.domain.save()

            await self.log_event("info", f"Started crawl job for {self.domain.original_url}", event_type="crawl_started")

            # Setup tools
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=self.job.max_workers)
            timeout = httpx.Timeout(self.job.timeout_seconds)

            async with httpx.AsyncClient(
                limits=limits,
                timeout=timeout,
                follow_redirects=self.job.follow_redirects,
                headers=DEFAULT_REQUEST_HEADERS,
            ) as client:
                self.sitemap_parser = SitemapParser(client, self.domain.domain, timeout=self.job.timeout_seconds)
                self.rate_limiter = RateLimiter(requests_per_second=10.0)
                self.issue_detector = IssueDetector()

                # Stage 1: Domain Validation
                await self._stage_domain_validation()

                # Stage 2: Sitemap Discovery
                await self._stage_sitemap_discovery()

                # Stage 3: HTTP Checking / Crawling URLs
                await self._stage_http_checking(client)

                # Stage 4: Duplication and Reporting
                await self._stage_reporting()

            # Mark Job as complete
            self.job.status = CrawlJobStatus.COMPLETED.value
            self.job.completed_at = datetime.utcnow()
            self.domain.status = DomainStatus.COMPLETED.value
            self.domain.last_crawl_at = datetime.utcnow()
            await self.job.save()
            await self.domain.save()

            await self.log_event("info", f"Successfully completed crawl job for {self.domain.original_url}", event_type="crawl_completed")

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

                    url_obj = await URL.find_one(
                        URL.domain_id == self.domain.id,
                        URL.url_hash == url_clean_hash
                    )

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
                        await url_obj.insert()
                    else:
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
                        url_obj.error_details = None
                        url_obj.crawl_attempt = 0
                        await url_obj.save()

                    total_urls += 1

                self.job.total_urls_found = total_urls
                self.domain.total_urls = total_urls
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

        if not urls:
            await self.log_event("warning", "No pending URLs found for crawling.", event_type="no_urls_found")
            return

        # Keep track of active task set and overall scheduled URL strings
        active_urls = set(u.url for u in urls)
        running_tasks = set()
        sem = asyncio.Semaphore(self.job.max_workers)

        async def crawl_and_release(url_to_crawl: URL):
            try:
                async with sem:
                    await self.rate_limiter.acquire_async()
                    await self._crawl_single_url(client, url_to_crawl)
            finally:
                running_tasks.discard(asyncio.current_task())

        # Spawn initial tasks
        for url_obj in urls:
            task = asyncio.create_task(crawl_and_release(url_obj))
            running_tasks.add(task)

        # Main polling loop to check for new dynamically queued URLs (link-discovered
        # during the crawl). 1s is plenty responsive here and avoids hammering Atlas
        # with a full collection scan 10x/sec for the entire crawl duration.
        while True:
            await asyncio.sleep(1.0)

            pending_urls = await URL.find(
                URL.domain_id == self.domain.id,
                URL.crawl_status == URLCrawlStatus.PENDING.value
            ).to_list(None)

            # Filter out URLs already in queue or processing
            new_urls = [u for u in pending_urls if u.url not in active_urls]

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
        url_obj.crawl_status = URLCrawlStatus.CHECKING.value
        url_obj.crawl_attempt += 1
        await url_obj.save()

        start_time = time.time()
        logger.info(f"Crawl HTTP request started: {url_obj.url}")

        try:
            # Fetch URL
            response = await client.get(url_obj.url, timeout=self.job.timeout_seconds)
            response_time_ms = int((time.time() - start_time) * 1000)

            # Update URL details (first phase commit)
            url_obj.status_code = response.status_code
            url_obj.final_url = str(response.url)
            url_obj.response_time_ms = response_time_ms
            url_obj.content_type = response.headers.get("content-type", "").split(";")[0].strip()
            url_obj.content_length = int(response.headers.get("content-length", 0))

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
            await url_obj.save()

            # Extract SEO data
            seo_data = None
            issues = []
            soup = None
            if "text/html" in url_obj.content_type:
                html_content = response.text
                try:
                    seo_data, soup = SEOExtractor.extract_all(html_content, url_obj.url, self.domain.domain, response_time_ms)
                    issues = self.issue_detector.detect_issues(seo_data)
                except Exception as e:
                    logger.error(f"Error parsing HTML for {url_obj.url}: {e}")

            for issue in issues:
                await self.log_event(
                    level=issue['type'],
                    message=f"{issue['category']} Issue ({issue['issue']}) on {url_obj.url}: {issue['details']}",
                    event_type="seo_issue_detected",
                    entity_type="url",
                    entity_id=str(url_obj.id),
                    details=issue
                )

            # Finalize URL check (second phase commit)
            if seo_data:
                # Check indexability
                robots = seo_data.get('robots', '').lower()
                url_obj.is_indexable = 'noindex' not in robots
                url_obj.canonical_url = seo_data.get('canonical_url')
                url_obj.robots_meta = seo_data.get('robots')
                url_obj.meta_data = seo_data

            url_obj.crawl_status = URLCrawlStatus.CHECKED.value
            url_obj.last_checked_at = datetime.utcnow()
            await url_obj.save()

            # self.job/self.domain are shared across all concurrent tasks, so the
            # increment+save is kept under the lock; everything above this is not.
            async with self.db_lock:
                self.job.total_urls_checked += 1
                self.domain.crawled_urls += 1
                await self.job.save()
                await self.domain.save()

            # Queue discovered internal links
            if soup:
                await self._extract_and_queue_links(soup, url_obj.url)

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

        # Periodic updates to the UI / stats (e.g. every 10 checked URLs)
        if self.job.total_urls_checked % 10 == 0:
            await self._update_job_progress()

    async def _update_job_progress(self):
        """Recalculate and update database stats on the CrawlJob"""
        async with self.db_lock:
            # Load stats for checked URLs in this job's domain
            checked_urls = await URL.find(
                URL.domain_id == self.domain.id,
                URL.crawl_status == URLCrawlStatus.CHECKED.value
            ).to_list(None)

            if not checked_urls:
                return

            total_checked = len(checked_urls)
            resp_times = [u.response_time_ms for u in checked_urls if u.response_time_ms is not None]
            avg_resp_time = int(sum(resp_times) / len(resp_times)) if resp_times else None

            # Reset counts
            c_2xx = c_3xx = c_4xx = c_5xx = c_timeout = c_dns = c_ssl = 0
            for url_obj in checked_urls:
                if url_obj.status_category == URLStatusCategory.TIMEOUT.value:
                    c_timeout += 1
                elif url_obj.status_category == URLStatusCategory.DNS_ERROR.value:
                    c_dns += 1
                elif url_obj.status_category == URLStatusCategory.SSL_ERROR.value:
                    c_ssl += 1
                elif url_obj.status_code:
                    if 200 <= url_obj.status_code < 300:
                        c_2xx += 1
                    elif 300 <= url_obj.status_code < 400:
                        c_3xx += 1
                    elif 400 <= url_obj.status_code < 500:
                        c_4xx += 1
                    elif url_obj.status_code >= 500:
                        c_5xx += 1

            self.job.avg_response_time_ms = avg_resp_time
            self.job.urls_2xx = c_2xx
            self.job.urls_3xx = c_3xx
            self.job.urls_4xx = c_4xx
            self.job.urls_5xx = c_5xx
            self.job.urls_timeout = c_timeout
            self.job.urls_dns_error = c_dns
            self.job.urls_ssl_error = c_ssl

            # Calculate speed
            elapsed_sec = (datetime.utcnow() - self.job.started_at).total_seconds()
            if elapsed_sec > 0:
                self.job.crawl_speed_urls_per_sec = round(total_checked / elapsed_sec, 2)

            await self.job.save()

    async def _stage_reporting(self):
        """Detect duplication, generate issues reports and populate statistics tables"""
        await self.log_event("info", "Starting Duplication check & Reporting stage", event_type="stage_reporting_started")

        # 1. Fetch checked HTML URLs for duplication checks
        checked_urls = await URL.find(
            URL.domain_id == self.domain.id,
            URL.crawl_status == URLCrawlStatus.CHECKED.value
        ).to_list(None)

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
            dup_issues = self.issue_detector.detect_duplication_issues(html_results)
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

    async def _get_or_create_spider_sitemap(self) -> uuid.UUID:
        """Get or create a virtual sitemap entry for HTML link discovery"""
        spider_url = f"https://{self.domain.domain}/html-spider"

        async with self.db_lock:
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

            return spider_sitemap.id

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
            
        # Get spider sitemap ID
        spider_sitemap_id = await self._get_or_create_spider_sitemap()
        
        # Deduplicate and check database
        async with self.db_lock:
            # Recheck limit inside the lock to be safe
            if self.job.total_urls_found >= 10000:
                return

            for url_str in set(new_urls):
                url_clean_hash = get_url_hash(url_str)
                existing_url = await URL.find_one(
                    URL.domain_id == self.domain.id,
                    URL.url_hash == url_clean_hash
                )
                if not existing_url:
                    new_url_obj = URL(
                        id=uuid.uuid4(),
                        domain_id=self.domain.id,
                        sitemap_id=spider_sitemap_id,
                        url=url_str,
                        url_hash=url_clean_hash,
                        crawl_status=URLCrawlStatus.PENDING.value,
                        meta_data={}
                    )
                    await new_url_obj.insert()
                    self.job.total_urls_found += 1

                    if self.job.total_urls_found >= 10000:
                        break
            await self.job.save()
