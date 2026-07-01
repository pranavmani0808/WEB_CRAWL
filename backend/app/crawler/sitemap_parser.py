"""Sitemap discovery and parsing (Async version)"""
import gzip
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, urljoin
import httpx
import logging

logger = logging.getLogger(__name__)

class SitemapParser:
    """Discovers and parses sitemap.xml files asynchronously"""

    def __init__(self, client: httpx.AsyncClient, base_domain: str, timeout: int = 10):
        self.client = client
        self.base_domain = base_domain
        self.timeout = timeout

    async def discover_sitemaps(self, base_url: str, on_sitemap_parsed=None):
        """
        Discover and parse sitemap.xml files.
        Returns:
            dict: A dictionary mapping sitemap_url -> list of URLs found in that sitemap
                  It also records whether it's an index and any parent-child relationships.
        """
        parsed_base = urlparse(base_url)
        scheme_netloc = f"{parsed_base.scheme}://{parsed_base.netloc}"

        # Common sitemap locations
        candidate_urls = [
            f"{scheme_netloc}/sitemap.xml",
            f"{scheme_netloc}/sitemap_index.xml",
            f"{scheme_netloc}/sitemaps.xml",
            f"{scheme_netloc}/sitemap/sitemap.xml"
        ]

        # Check robots.txt for sitemap declarations
        robots_sitemaps = await self._get_sitemaps_from_robots(scheme_netloc)
        candidate_urls.extend(robots_sitemaps)

        # De-duplicate candidate URLs
        candidate_urls = list(set(candidate_urls))

        logger.info(f"Discovering sitemaps for {self.base_domain} from candidate list: {candidate_urls}")

        discovered_sitemaps = {}  # sitemap_url -> {urls: [...], is_index: bool, parent: str/None}
        
        for sitemap_url in candidate_urls:
            try:
                await self._parse_sitemap_recursive(sitemap_url, discovered_sitemaps, depth=1, on_sitemap_parsed=on_sitemap_parsed)
            except Exception as e:
                logger.error(f"Failed to parse candidate sitemap {sitemap_url}: {e}")

        return discovered_sitemaps

    async def _get_sitemaps_from_robots(self, scheme_netloc: str):
        """Extract sitemap URLs from robots.txt"""
        sitemaps = []
        try:
            robots_url = f"{scheme_netloc}/robots.txt"
            response = await self.client.get(robots_url, timeout=self.timeout)

            if response.status_code == 200:
                for line in response.text.split('\n'):
                    line = line.strip()
                    if line.lower().startswith('sitemap:'):
                        parts = line.split(':', 1)
                        if len(parts) > 1:
                            sitemap_url = parts[1].strip()
                            sitemaps.append(sitemap_url)
        except Exception as e:
            logger.warning(f"Could not fetch or parse robots.txt for sitemaps: {e}")

        return sitemaps

    async def _parse_sitemap_recursive(self, sitemap_url: str, discovered_sitemaps: dict, depth: int = 1, max_depth: int = 10, parent_url: str = None, on_sitemap_parsed=None):
        """
        Parse a sitemap.xml file recursively (handling sitemap indexes).
        Updates discovered_sitemaps dict in place.
        """
        if depth > max_depth or sitemap_url in discovered_sitemaps:
            return

        try:
            logger.info(f"Fetching sitemap: {sitemap_url}")
            response = await self.client.get(sitemap_url, timeout=self.timeout)

            if response.status_code != 200:
                logger.warning(f"Sitemap {sitemap_url} returned status code {response.status_code}")
                discovered_sitemaps[sitemap_url] = {
                    'urls': [],
                    'is_index': False,
                    'parent_sitemap_url': parent_url,
                    'response_code': response.status_code,
                    'status': 'failed',
                    'error_message': f"Returned status code {response.status_code}"
                }
                if on_sitemap_parsed:
                    await on_sitemap_parsed(sitemap_url, discovered_sitemaps[sitemap_url])
                return

            # Handle compressed sitemaps
            content = response.content
            if sitemap_url.endswith('.gz') or response.headers.get('content-encoding') == 'gzip':
                try:
                    content = gzip.decompress(content)
                except Exception as e:
                    logger.error(f"Failed to decompress gzipped sitemap {sitemap_url}: {e}")

            # Parse XML
            try:
                root = ET.fromstring(content)
            except ET.ParseError as e:
                logger.error(f"XML parse error for {sitemap_url}: {e}")
                discovered_sitemaps[sitemap_url] = {
                    'urls': [],
                    'is_index': False,
                    'parent_sitemap_url': parent_url,
                    'response_code': response.status_code,
                    'status': 'failed',
                    'error_message': f"XML parse error: {str(e)}"
                }
                if on_sitemap_parsed:
                    await on_sitemap_parsed(sitemap_url, discovered_sitemaps[sitemap_url])
                return

            # Remove namespace prefixes (e.g. {http://www.sitemaps.org/schemas/sitemap/0.9})
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}')[1]

            # Detect if this is a sitemap index (contains other sitemaps)
            nested_sitemap_elems = root.findall('.//sitemap')
            is_index = len(nested_sitemap_elems) > 0

            discovered_sitemaps[sitemap_url] = {
                'urls': [],
                'is_index': is_index,
                'parent_sitemap_url': parent_url,
                'response_code': response.status_code,
                'status': 'fetched'
            }

            if is_index:
                if on_sitemap_parsed:
                    await on_sitemap_parsed(sitemap_url, discovered_sitemaps[sitemap_url])
                logger.info(f"Found sitemap index with {len(nested_sitemap_elems)} nested sitemaps in {sitemap_url}")
                for sitemap_elem in nested_sitemap_elems:
                    loc_elem = sitemap_elem.find('loc')
                    if loc_elem is not None and loc_elem.text:
                        nested_url = loc_elem.text.strip()
                        await self._parse_sitemap_recursive(
                            nested_url, 
                            discovered_sitemaps, 
                            depth + 1, 
                            max_depth, 
                            parent_url=sitemap_url,
                            on_sitemap_parsed=on_sitemap_parsed
                        )
            else:
                # Extract URLs from sitemap
                url_elems = root.findall('.//url')
                logger.info(f"Found {len(url_elems)} URLs in sitemap {sitemap_url}")
                for url_elem in url_elems:
                    loc_elem = url_elem.find('loc')
                    if loc_elem is not None and loc_elem.text:
                        url = loc_elem.text.strip()
                        # Extract other optional fields from sitemap url definition
                        lastmod_elem = url_elem.find('lastmod')
                        changefreq_elem = url_elem.find('changefreq')
                        priority_elem = url_elem.find('priority')

                        discovered_sitemaps[sitemap_url]['urls'].append({
                            'url': url,
                            'lastmod': lastmod_elem.text.strip() if lastmod_elem is not None and lastmod_elem.text else None,
                            'changefreq': changefreq_elem.text.strip() if changefreq_elem is not None and changefreq_elem.text else None,
                            'priority': float(priority_elem.text.strip()) if priority_elem is not None and priority_elem.text else None
                        })
                if on_sitemap_parsed:
                    await on_sitemap_parsed(sitemap_url, discovered_sitemaps[sitemap_url])

        except Exception as e:
            logger.error(f"Error parsing sitemap {sitemap_url}: {e}")
            discovered_sitemaps[sitemap_url] = {
                'urls': [],
                'is_index': False,
                'parent_sitemap_url': parent_url,
                'response_code': getattr(e, 'response', None).status_code if hasattr(e, 'response') and e.response else None,
                'status': 'failed',
                'error_message': str(e)
            }
            if on_sitemap_parsed:
                await on_sitemap_parsed(sitemap_url, discovered_sitemaps[sitemap_url])
