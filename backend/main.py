import asyncio
import logging
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from app.core.config import settings
from app.core.exceptions import CrawlerException
from app.core.security import create_access_token, create_refresh_token, get_password_hash, verify_password
from app.core.auth_deps import get_current_user
from app.database.database import init_db, close_db
from app.models.domain import Domain
from app.models.crawl_job import CrawlJob
from app.models.url import URL
from app.models.crawl_log import CrawlLog
from app.models.crawl_statistics import CrawlStatistics
from app.models.user import User
from app.models.report import Report
from app.models.url_snapshot import UrlSnapshot
from app.models.crawl_schedule import CrawlSchedule
from app.workers.tasks import crawl_domain_task, SCHEDULE_INTERVALS
from app.reports.pdf_generator import generate_crawl_pdf
from app.crawler import ssrf_guard
import uuid
from urllib.parse import urlparse
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded


def _client_ip(request: Request) -> str:
    """Real client IP for rate limiting. Behind Railway's proxy the socket
    peer is the proxy, so prefer the first X-Forwarded-For entry."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_client_ip)

logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Rate limiting (slowapi): protects auth endpoints from brute-force /
# mass-registration. Returns HTTP 429 when a client exceeds the limit.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# MongoDB Lifecycle
@app.on_event("startup")
async def startup_db():
    await init_db()

@app.on_event("shutdown")
async def shutdown_db():
    await close_db()

# CORS Setup
origins = []
if isinstance(settings.CORS_ORIGINS, list):
    origins = [str(origin).rstrip("/") for origin in settings.CORS_ORIGINS]
else:
    origins = [str(settings.CORS_ORIGINS).rstrip("/")]

# Always include localhost:3000 for local development
if "http://localhost:3000" not in origins and "*" not in origins:
    origins.append("http://localhost:3000")

# Add wildcard support if configured
if "*" in origins:
    origins = ["*"]

import re

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Compress large JSON responses. The audited-URLs payload (which carries full
# per-page SEO metadata) is ~600KB uncompressed on a mid-size crawl and
# compresses ~10x - without this the transfer time dwarfed the query time for
# anyone not sitting next to the server.
app.add_middleware(GZipMiddleware, minimum_size=1024)

def _cors_headers(request: Request) -> dict:
    """Return CORS headers so error responses aren't blocked by the browser."""
    origin = request.headers.get("origin", "")
    if "*" in origins or origin in origins or (origin and re.match(r"https?://(localhost|127\.0\.0\.1)(:\d+)?", origin)):
        return {
            "Access-Control-Allow-Origin": origin or "*",
            "Access-Control-Allow-Credentials": "true",
        }
    return {}

# Exception handlers
@app.exception_handler(CrawlerException)
async def crawler_exception_handler(request: Request, exc: CrawlerException):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        headers=_cors_headers(request),
        content={
            "error": exc.code,
            "message": exc.message,
            "details": exc.details
        }
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        headers=_cors_headers(request),
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred on the server.",
            "details": {"system_error": str(exc)}
        }
    )

# Basic endpoints
@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect root access to API docs."""
    return RedirectResponse(url="/docs")

@app.get("/health", tags=["Health"])
async def health_check():
    """Simple API health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "project": settings.PROJECT_NAME
    }

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str = Field(min_length=8)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


def _user_public(user: User) -> dict:
    return {"id": str(user.id), "email": user.email, "username": user.username, "is_admin": user.is_admin}


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """Auth dependency that requires the caller to be an admin."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@app.post("/api/auth/register", tags=["Auth"])
@limiter.limit("5/minute")
async def register(request: Request, req: RegisterRequest):
    """Create a new user account."""
    existing = await User.find_one(User.email == req.email)
    if existing:
        return JSONResponse(status_code=409, content={"message": "An account with this email already exists"})

    existing_username = await User.find_one(User.username == req.username)
    if existing_username:
        return JSONResponse(status_code=409, content={"message": "This username is already taken"})

    user = User(
        email=req.email,
        username=req.username,
        password_hash=get_password_hash(req.password),
    )
    await user.insert()

    return AuthResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=_user_public(user),
    )


@app.post("/api/auth/login", tags=["Auth"])
@limiter.limit("10/minute")
async def login(request: Request, req: LoginRequest):
    """Authenticate with email + password and receive JWT tokens."""
    user = await User.find_one(User.email == req.email.strip().lower())
    if not user or not verify_password(req.password, user.password_hash):
        return JSONResponse(status_code=401, content={"message": "Incorrect email or password"})

    if not user.is_active:
        return JSONResponse(status_code=403, content={"message": "This account has been deactivated"})

    return AuthResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=_user_public(user),
    )


@app.get("/api/auth/me", tags=["Auth"])
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return _user_public(current_user)


# ---------------------------------------------------------------------------
# Crawl
# ---------------------------------------------------------------------------

class CrawlRequest(BaseModel):
    url: str

@app.post("/api/crawl", tags=["Crawl"])
async def start_crawl_endpoint(req: CrawlRequest, current_user: User = Depends(get_current_user)):
    """Start a crawl job for the specified URL"""
    # Fairness (A): cap how many crawls one user can have in flight at once so
    # a single user can't fill every worker slot and starve everyone else.
    active_count = await CrawlJob.find(
        CrawlJob.user_id == current_user.id,
        {"status": {"$in": ["pending", "running", "stopping"]}},
    ).count()
    if active_count >= settings.MAX_CONCURRENT_CRAWLS_PER_USER:
        return JSONResponse(
            status_code=429,
            content={"message": (
                f"You already have {active_count} crawls running. "
                f"Please wait for one to finish (limit {settings.MAX_CONCURRENT_CRAWLS_PER_USER} at a time)."
            )},
        )

    url = req.url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    parsed = urlparse(url)
    # Hostnames are case-insensitive (DNS), so lowercase the host when
    # normalizing. Without this, "Ahrefs.com" and "ahrefs.com" created two
    # separate domain records for the same site - which then collided on the
    # global-unique url_hash index and crashed re-crawls.
    domain_name = (parsed.netloc or parsed.path.split('/')[0]).lower()

    # SSRF guard at the entry point: reject internal/private targets before we
    # ever fetch robots.txt/sitemaps/pages from them. The crawler enforces
    # this again per-URL (defense in depth), but blocking here stops the very
    # first request. DNS lookup is blocking, so run it off the event loop.
    import asyncio as _asyncio
    ssrf_reason = await _asyncio.to_thread(ssrf_guard.blocked_reason, f"{parsed.scheme.lower()}://{domain_name}")
    if ssrf_reason:
        return JSONResponse(status_code=400, content={"message": f"This URL can't be crawled: {ssrf_reason}"})

    user_id = current_user.id

    # Get or create Domain
    normalized_url = f"{parsed.scheme.lower()}://{domain_name}"
    domain = await Domain.find_one(Domain.normalized_url == normalized_url)

    if not domain:
        domain = Domain(
            user_id=user_id,
            original_url=url,
            normalized_url=normalized_url,
            domain=domain_name,
            status="pending"
        )
        await domain.insert()

    # Create Crawl Job
    job = CrawlJob(
        domain_id=domain.id,
        user_id=user_id,
        status="pending",
        max_workers=settings.CRAWLER_MAX_WORKERS,
        timeout_seconds=settings.CRAWLER_TIMEOUT_SECONDS,
        respect_robots_txt=settings.CRAWLER_RESPECT_ROBOTS_TXT,
        follow_redirects=settings.CRAWLER_FOLLOW_REDIRECTS
    )
    await job.insert()

    # Dispatch Celery task
    crawl_domain_task.delay(str(job.id))

    return {"job_id": str(job.id), "domain_id": str(domain.id)}

@app.get("/api/crawl/jobs", tags=["Crawl"])
async def list_crawl_jobs(current_user: User = Depends(get_current_user)):
    """List all crawl jobs belonging to the current user, with associated domains"""
    jobs = await CrawlJob.find(CrawlJob.user_id == current_user.id).sort("-created_at").to_list(None)

    # Batch fetch domains to avoid N+1 query overhead
    domain_ids = list({j.domain_id for j in jobs})
    domains = await Domain.find({"_id": {"$in": domain_ids}}).to_list(None)
    domains_map = {d.id: d for d in domains}

    result = []
    for j in jobs:
        domain = domains_map.get(j.domain_id)
        result.append({
            "id": str(j.id),
            "status": j.status,
            "domain": domain.domain if domain else "unknown",
            "url": domain.original_url if domain else "unknown",
            "total_urls_found": j.total_urls_found,
            "total_urls_checked": j.total_urls_checked,
            "created_at": j.created_at.isoformat()
        })

    return result

@app.get("/api/crawl/jobs/{job_id}", tags=["Crawl"])
async def get_crawl_job(job_id: str, current_user: User = Depends(get_current_user)):
    """Get details, stats and logs for a specific crawl job"""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    job = await CrawlJob.get(job_uuid)

    if not job or job.user_id != current_user.id:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    # Fetch domain, logs and statistics concurrently - these are independent
    # queries, and the API-to-Atlas round-trip is the dominant cost per query
    # (the DB lives in a different region than the API), so running them
    # sequentially tripled this endpoint's latency for no reason. Logs are
    # capped to the most recent 200: this endpoint is polled every few
    # seconds while a crawl runs, and big crawls generate thousands of
    # per-URL issue logs. Fetch newest-first (matching the index), then flip
    # back to chronological for the UI.
    domain, logs, stats = await asyncio.gather(
        Domain.get(job.domain_id),
        # _id tiebreaker keeps logs written within the same millisecond in
        # insertion order (timestamps only have ms precision).
        CrawlLog.find(CrawlLog.crawl_job_id == job_uuid).sort([("timestamp", -1), ("_id", -1)]).limit(200).to_list(),
        CrawlStatistics.find_one(CrawlStatistics.crawl_job_id == job_uuid),
    )
    logs.reverse()

    return {
        "id": str(job.id),
        "status": job.status,
        "domain": domain.domain if domain else "unknown",
        "url": domain.original_url if domain else "unknown",
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "stages": {
            "domain_validation": job.stage_domain_validation,
            "dns_resolution": job.stage_dns_resolution,
            "ssl_verification": job.stage_ssl_verification,
            "robots_found": job.stage_robots_found,
            "sitemap_discovery": job.stage_sitemap_discovery,
            "parsing_indexes": job.stage_parsing_indexes,
            "parsing_sitemaps": job.stage_parsing_sitemaps,
            "url_discovery": job.stage_url_discovery,
            "http_checking": job.stage_http_checking
        },
        "progress": {
            "total_sitemaps_found": job.total_sitemaps_found,
            "total_urls_found": job.total_urls_found,
            "total_urls_checked": job.total_urls_checked,
            "urls_2xx": job.urls_2xx,
            "urls_3xx": job.urls_3xx,
            "urls_4xx": job.urls_4xx,
            "urls_5xx": job.urls_5xx,
            "urls_timeout": job.urls_timeout,
            "urls_dns_error": job.urls_dns_error
        },
        "stats": {
            "health_score": stats.health_score if stats else None,
            "avg_response_time_ms": job.avg_response_time_ms,
            "speed_urls_per_sec": float(job.crawl_speed_urls_per_sec) if job.crawl_speed_urls_per_sec else 0.0
        } if stats else None,
        "logs": [{
            "timestamp": l.timestamp.isoformat(),
            "level": l.level,
            "message": l.message
        } for l in logs]
    }

@app.get("/api/crawl/jobs/{job_id}/urls", tags=["Crawl"])
async def list_job_urls(job_id: str, current_user: User = Depends(get_current_user)):
    """List all URLs crawled for a specific job"""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    # Fetch job
    job = await CrawlJob.get(job_uuid)
    if not job or job.user_id != current_user.id:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    # URLs are stored per-domain (reused/updated across crawl runs, not
    # per-job), so a plain domain_id filter would surface stale results from
    # a previous crawl of the same domain before this job has touched them.
    # Restrict to URLs this job's own run has actually created/updated.
    #
    # Project away meta_data/seo_issues server-side: they're ~90% of each
    # document's weight, the table view never renders them, and shipping
    # them from Atlas (which sits in a different region than the API) made
    # this endpoint take >10s on mid-size crawls. The two image counts the
    # CSV export needs are computed inside the projection, and the full
    # per-page payload is served by the /urls/{url_id} endpoint below when
    # the detail modal actually opens.
    images = {"$ifNull": ["$meta_data.images", []]}
    rows = await URL.find(
        URL.domain_id == job.domain_id,
        URL.updated_at >= job.started_at,
    ).aggregate([
        {"$project": {
            "_id": 1,
            "url": 1,
            "status_code": 1,
            "status_category": 1,
            "response_time_ms": 1,
            "content_type": 1,
            "canonical_url": 1,
            "is_indexable": 1,
            "crawl_status": 1,
            "images_count": {"$size": images},
            "images_missing_alt": {"$size": {"$filter": {
                "input": images,
                "as": "img",
                "cond": {"$eq": [{"$ifNull": ["$$img.alt", ""]}, ""]},
            }}},
            "seo_issues_count": {"$size": {"$ifNull": ["$seo_issues", []]}},
        }},
        {"$sort": {"url": 1}},
    ]).to_list()

    def _id_str(v):
        # Raw aggregation rows bypass Beanie's field decoding, so _id may
        # come back as a bson Binary (uuid subtype) instead of a UUID.
        if isinstance(v, uuid.UUID):
            return str(v)
        try:
            return str(uuid.UUID(bytes=bytes(v)))
        except (TypeError, ValueError):
            return str(v)

    return [{
        "id": _id_str(r["_id"]),
        "url": r.get("url"),
        "status_code": r.get("status_code"),
        "status_category": r.get("status_category"),
        "response_time_ms": r.get("response_time_ms"),
        "content_type": r.get("content_type"),
        "canonical_url": r.get("canonical_url"),
        "is_indexable": r.get("is_indexable"),
        "crawl_status": r.get("crawl_status"),
        "images_count": r.get("images_count", 0),
        "images_missing_alt": r.get("images_missing_alt", 0),
        "seo_issues_count": r.get("seo_issues_count", 0),
    } for r in rows]


@app.get("/api/crawl/jobs/{job_id}/urls/{url_id}", tags=["Crawl"])
async def get_job_url_detail(job_id: str, url_id: str, current_user: User = Depends(get_current_user)):
    """Full detail for one audited URL (SEO metadata + issues) - fetched on
    demand when the page-detail modal opens, so the list endpoint doesn't
    have to carry this weight for every row."""
    try:
        job_uuid = uuid.UUID(job_id)
        url_uuid = uuid.UUID(url_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid ID format"})

    job = await CrawlJob.get(job_uuid)
    if not job or job.user_id != current_user.id:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    u = await URL.get(url_uuid)
    if not u or u.domain_id != job.domain_id:
        return JSONResponse(status_code=404, content={"message": "URL not found"})

    return {
        "id": str(u.id),
        "url": u.url,
        "status_code": u.status_code,
        "status_category": u.status_category,
        "response_time_ms": u.response_time_ms,
        "content_type": u.content_type,
        "canonical_url": u.canonical_url,
        "is_indexable": u.is_indexable,
        "crawl_status": u.crawl_status,
        "metadata": u.meta_data,
        "seo_issues": u.seo_issues,
    }


@app.get("/api/crawl/jobs/{job_id}/pdf", tags=["Crawl"])
async def download_job_pdf(job_id: str, current_user: User = Depends(get_current_user)):
    """Generate and download a PDF audit report for a completed crawl job."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    job = await CrawlJob.get(job_uuid)
    if not job or job.user_id != current_user.id:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    domain = await Domain.get(job.domain_id)
    if not domain:
        return JSONResponse(status_code=404, content={"message": "Domain not found"})

    urls = await URL.find(
        URL.domain_id == job.domain_id,
        URL.updated_at >= job.started_at,
    ).sort("url").to_list(None)

    category_reports = await Report.find(Report.crawl_job_id == job_uuid).to_list(None)

    pdf_bytes = generate_crawl_pdf(job, domain, urls, category_reports)

    filename = f"{domain.domain}_audit_report.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/crawl/jobs/{job_id}/comparable", tags=["Crawl"])
async def list_comparable_jobs(job_id: str, current_user: User = Depends(get_current_user)):
    """List other completed jobs for the same domain that have snapshot data
    to compare against (jobs run before the comparison feature shipped have
    no snapshot and can't be compared)."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    job = await CrawlJob.get(job_uuid)
    if not job or job.user_id != current_user.id:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    other_jobs = await CrawlJob.find(
        CrawlJob.domain_id == job.domain_id,
        CrawlJob.status == "completed",
        CrawlJob.user_id == current_user.id,
    ).sort("-created_at").to_list(None)

    comparable = []
    for j in other_jobs:
        if j.id == job_uuid:
            continue
        has_snapshot = await UrlSnapshot.find_one(UrlSnapshot.crawl_job_id == j.id)
        if has_snapshot:
            comparable.append({
                "id": str(j.id),
                "created_at": j.created_at.isoformat(),
                "total_urls_checked": j.total_urls_checked,
            })

    return comparable


@app.get("/api/crawl/jobs/{job_id}/compare/{other_job_id}", tags=["Crawl"])
async def compare_crawl_jobs(job_id: str, other_job_id: str, current_user: User = Depends(get_current_user)):
    """Diff two completed crawl jobs for the same domain using their frozen
    UrlSnapshot records (live URL documents get overwritten by newer crawls,
    so the snapshot is the only reliable source for an older job's results)."""
    try:
        job_a_uuid = uuid.UUID(job_id)
        job_b_uuid = uuid.UUID(other_job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    job_a = await CrawlJob.get(job_a_uuid)
    job_b = await CrawlJob.get(job_b_uuid)
    if not job_a or job_a.user_id != current_user.id or not job_b or job_b.user_id != current_user.id:
        return JSONResponse(status_code=404, content={"message": "Job not found"})
    if job_a.domain_id != job_b.domain_id:
        return JSONResponse(status_code=400, content={"message": "Jobs must be for the same domain"})

    # Order chronologically regardless of which one was passed as job_id
    older, newer = (job_a, job_b) if job_a.created_at <= job_b.created_at else (job_b, job_a)

    older_snaps = await UrlSnapshot.find(UrlSnapshot.crawl_job_id == older.id).to_list(None)
    newer_snaps = await UrlSnapshot.find(UrlSnapshot.crawl_job_id == newer.id).to_list(None)

    if not older_snaps or not newer_snaps:
        return JSONResponse(status_code=404, content={"message": "One or both jobs have no snapshot data to compare (crawled before this feature was added)"})

    older_by_hash = {s.url_hash: s for s in older_snaps}
    newer_by_hash = {s.url_hash: s for s in newer_snaps}

    def is_broken(status_category):
        return status_category in ("client_error", "server_error", "timeout", "dns_error")

    added_urls = [newer_by_hash[h].url for h in newer_by_hash if h not in older_by_hash]
    removed_urls = [older_by_hash[h].url for h in older_by_hash if h not in newer_by_hash]

    newly_broken, newly_fixed, status_changes = [], [], []
    for h, new_snap in newer_by_hash.items():
        old_snap = older_by_hash.get(h)
        if not old_snap:
            continue
        if old_snap.status_code != new_snap.status_code:
            entry = {"url": new_snap.url, "old_status": old_snap.status_code, "new_status": new_snap.status_code}
            status_changes.append(entry)
            if not is_broken(old_snap.status_category) and is_broken(new_snap.status_category):
                newly_broken.append(entry)
            elif is_broken(old_snap.status_category) and not is_broken(new_snap.status_category):
                newly_fixed.append(entry)

    return {
        "older_job": {"id": str(older.id), "created_at": older.created_at.isoformat(), "total_urls_checked": older.total_urls_checked},
        "newer_job": {"id": str(newer.id), "created_at": newer.created_at.isoformat(), "total_urls_checked": newer.total_urls_checked},
        "summary": {
            "urls_added": len(added_urls),
            "urls_removed": len(removed_urls),
            "newly_broken": len(newly_broken),
            "newly_fixed": len(newly_fixed),
            "status_changed": len(status_changes),
        },
        "added_urls": added_urls[:200],
        "removed_urls": removed_urls[:200],
        "newly_broken": newly_broken[:200],
        "newly_fixed": newly_fixed[:200],
        "status_changes": status_changes[:200],
    }


@app.post("/api/crawl/jobs/{job_id}/retry", tags=["Crawl"])
async def retry_crawl_job(job_id: str, current_user: User = Depends(get_current_user)):
    """Re-dispatch a stuck or failed crawl job back into the Celery queue."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    job = await CrawlJob.get(job_uuid)

    if not job or job.user_id != current_user.id:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    # Reset job status so the engine re-runs it
    job.status = "pending"
    job.total_urls_found = 0
    job.total_urls_checked = 0
    job.urls_2xx = 0
    job.urls_3xx = 0
    job.urls_4xx = 0
    job.urls_5xx = 0
    job.urls_timeout = 0
    job.urls_dns_error = 0
    job.completed_at = None
    await job.save()

    # Re-dispatch Celery task
    crawl_domain_task.delay(str(job.id))
    return {"message": "Job re-dispatched", "job_id": str(job.id)}


@app.post("/api/crawl/jobs/retry-pending", tags=["Crawl"])
async def retry_all_pending_jobs(current_user: User = Depends(get_current_user)):
    """Re-dispatch all of the current user's stuck jobs (pending or failed).

    Must match the frontend's "stuck job" definition (status pending OR
    failed) - this used to only touch "pending" jobs, so a "failed" job left
    the "Jobs stuck?" banner permanently stuck since Retry All was a silent
    no-op for it.
    """
    jobs = await CrawlJob.find(
        {"status": {"$in": ["pending", "failed"]}},
        CrawlJob.user_id == current_user.id,
    ).to_list(None)

    dispatched = []
    for job in jobs:
        job.status = "pending"
        job.total_urls_found = 0
        job.total_urls_checked = 0
        job.urls_2xx = 0
        job.urls_3xx = 0
        job.urls_4xx = 0
        job.urls_5xx = 0
        job.urls_timeout = 0
        job.urls_dns_error = 0
        job.completed_at = None
        await job.save()
        crawl_domain_task.delay(str(job.id))
        dispatched.append(str(job.id))

    return {"message": f"Re-dispatched {len(dispatched)} jobs", "job_ids": dispatched}


@app.post("/api/crawl/jobs/{job_id}/pause", tags=["Crawl"])
async def pause_crawl_job(job_id: str, current_user: User = Depends(get_current_user)):
    """Pause a running crawl job by marking its status as paused."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    job = await CrawlJob.get(job_uuid)

    if not job or job.user_id != current_user.id:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    if job.status not in ("running", "pending"):
        return JSONResponse(
            status_code=400,
            content={"message": f"Cannot pause a job in '{job.status}' state"}
        )

    job.status = "paused"
    await job.save()
    return {"message": "Job paused", "job_id": str(job.id)}


@app.post("/api/crawl/jobs/{job_id}/resume", tags=["Crawl"])
async def resume_crawl_job(job_id: str, current_user: User = Depends(get_current_user)):
    """Resume a paused crawl job by re-dispatching it."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    job = await CrawlJob.get(job_uuid)

    if not job or job.user_id != current_user.id:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    if job.status != "paused":
        return JSONResponse(
            status_code=400,
            content={"message": f"Cannot resume a job in '{job.status}' state"}
        )

    job.status = "pending"
    await job.save()
    crawl_domain_task.delay(str(job.id))
    return {"message": "Job resumed", "job_id": str(job.id)}


@app.post("/api/crawl/jobs/{job_id}/cancel", tags=["Crawl"])
async def cancel_crawl_job(job_id: str, current_user: User = Depends(get_current_user)):
    """Request that a running/pending crawl job stop.

    This only flips the status to "stopping" - the crawler engine polls for
    that on its own (see CrawlerEngine._check_cancelled) and does the actual
    teardown, since it's the only thing that can safely cancel the in-flight
    asyncio tasks and close the shared httpx client. The job settles into
    "cancelled" within a few seconds once the engine notices.
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    job = await CrawlJob.get(job_uuid)

    if not job or job.user_id != current_user.id:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    if job.status not in ("running", "pending"):
        return JSONResponse(
            status_code=400,
            content={"message": f"Cannot cancel a job in '{job.status}' state"}
        )

    job.status = "stopping"
    await job.save()
    return {"message": "Cancellation requested", "job_id": str(job.id)}


@app.delete("/api/crawl/jobs/{job_id}", tags=["Crawl"])
async def delete_crawl_job(job_id: str, current_user: User = Depends(get_current_user)):
    """Permanently delete a crawl job and all associated data."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    job = await CrawlJob.get(job_uuid)

    if not job or job.user_id != current_user.id:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    # Delete associated logs
    await CrawlLog.find(CrawlLog.crawl_job_id == job_uuid).delete()
    # Delete the job itself
    await job.delete()
    return {"message": "Job deleted", "job_id": job_id}



# ---------------------------------------------------------------------------
# Scheduled / recurring audits
# ---------------------------------------------------------------------------

from datetime import datetime as _datetime


class ScheduleRequest(BaseModel):
    frequency: str

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in SCHEDULE_INTERVALS:
            raise ValueError(f"frequency must be one of: {', '.join(SCHEDULE_INTERVALS)}")
        return v


async def _schedule_public(s: CrawlSchedule, domains_map: dict = None) -> dict:
    if domains_map is not None:
        domain = domains_map.get(s.domain_id)
    else:
        domain = await Domain.get(s.domain_id)
    return {
        "id": str(s.id),
        "domain_id": str(s.domain_id),
        "domain": domain.domain if domain else "unknown",
        "frequency": s.frequency,
        "enabled": s.enabled,
        "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
    }


@app.post("/api/crawl/jobs/{job_id}/schedule", tags=["Schedules"])
async def create_schedule_for_job(job_id: str, req: ScheduleRequest, current_user: User = Depends(get_current_user)):
    """Create (or update) a recurring audit for the domain a job crawled.

    One schedule per (user, domain): scheduling an already-scheduled domain
    just changes its frequency. The first scheduled run is one interval from
    now - the user typically just crawled the domain manually.
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    job = await CrawlJob.get(job_uuid)
    if not job or job.user_id != current_user.id:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    schedule = await CrawlSchedule.find_one(
        CrawlSchedule.domain_id == job.domain_id,
        CrawlSchedule.user_id == current_user.id,
    )
    next_run = _datetime.utcnow() + SCHEDULE_INTERVALS[req.frequency]
    if schedule:
        schedule.frequency = req.frequency
        schedule.enabled = True
        schedule.next_run_at = next_run
        await schedule.save()
    else:
        schedule = CrawlSchedule(
            domain_id=job.domain_id,
            user_id=current_user.id,
            frequency=req.frequency,
            next_run_at=next_run,
        )
        await schedule.insert()

    return await _schedule_public(schedule)


@app.get("/api/crawl/schedules", tags=["Schedules"])
async def list_schedules(current_user: User = Depends(get_current_user)):
    """List the current user's recurring audits."""
    schedules = await CrawlSchedule.find(CrawlSchedule.user_id == current_user.id).to_list()
    domain_ids = list({s.domain_id for s in schedules})
    domains = await Domain.find({"_id": {"$in": domain_ids}}).to_list() if domain_ids else []
    domains_map = {d.id: d for d in domains}
    return [await _schedule_public(s, domains_map) for s in schedules]


@app.delete("/api/crawl/schedules/{schedule_id}", tags=["Schedules"])
async def delete_schedule(schedule_id: str, current_user: User = Depends(get_current_user)):
    """Remove a recurring audit."""
    try:
        schedule_uuid = uuid.UUID(schedule_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid schedule ID format"})

    schedule = await CrawlSchedule.get(schedule_uuid)
    if not schedule or schedule.user_id != current_user.id:
        return JSONResponse(status_code=404, content={"message": "Schedule not found"})

    await schedule.delete()
    return {"message": "Schedule deleted", "schedule_id": schedule_id}


# ---------------------------------------------------------------------------
# Admin dashboard (admin-only)
# ---------------------------------------------------------------------------

from datetime import timedelta as _timedelta


@app.get("/api/admin/overview", tags=["Admin"])
async def admin_overview(admin: User = Depends(get_current_admin)):
    """High-level platform metrics for the admin dashboard."""
    now = _datetime.utcnow()
    week_ago = now - _timedelta(days=7)

    total_users = await User.find().count()
    active_users = await User.find(User.is_active == True).count()  # noqa: E712
    new_users_7d = await User.find(User.created_at >= week_ago).count()

    total_jobs = await CrawlJob.find().count()
    running_jobs = await CrawlJob.find({"status": {"$in": ["running", "pending", "stopping"]}}).count()
    completed_jobs = await CrawlJob.find(CrawlJob.status == "completed").count()
    failed_jobs = await CrawlJob.find(CrawlJob.status == "failed").count()
    jobs_7d = await CrawlJob.find(CrawlJob.created_at >= week_ago).count()

    total_domains = await Domain.find().count()

    # Total URLs audited across the platform (sum of a denormalized counter).
    urls_rows = await CrawlJob.find().aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$total_urls_checked"}}}
    ]).to_list()
    total_urls_checked = urls_rows[0]["total"] if urls_rows else 0

    return {
        "users": {"total": total_users, "active": active_users, "new_last_7d": new_users_7d},
        "crawls": {
            "total": total_jobs, "running": running_jobs, "completed": completed_jobs,
            "failed": failed_jobs, "last_7d": jobs_7d,
        },
        "domains": total_domains,
        "total_urls_checked": total_urls_checked,
        "generated_at": now.isoformat(),
    }


@app.get("/api/admin/users", tags=["Admin"])
async def admin_list_users(admin: User = Depends(get_current_admin)):
    """Every user with their crawl counts, computed in one pass."""
    users = await User.find().sort("-created_at").to_list()

    # Aggregate per-user crawl stats in one query instead of N.
    stats_rows = await CrawlJob.find().aggregate([
        {"$group": {
            "_id": "$user_id",
            "total_crawls": {"$sum": 1},
            "active_crawls": {"$sum": {"$cond": [{"$in": ["$status", ["running", "pending", "stopping"]]}, 1, 0]}},
            "urls_checked": {"$sum": "$total_urls_checked"},
            "last_crawl_at": {"$max": "$created_at"},
        }},
    ]).to_list()

    def _uid(v):
        if isinstance(v, uuid.UUID):
            return str(v)
        try:
            return str(uuid.UUID(bytes=bytes(v)))
        except (TypeError, ValueError):
            return str(v)

    stats_by_user = {_uid(r["_id"]): r for r in stats_rows if r.get("_id") is not None}

    result = []
    for u in users:
        s = stats_by_user.get(str(u.id), {})
        last = s.get("last_crawl_at")
        result.append({
            "id": str(u.id),
            "email": u.email,
            "username": u.username,
            "is_active": u.is_active,
            "is_admin": u.is_admin,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "total_crawls": s.get("total_crawls", 0),
            "active_crawls": s.get("active_crawls", 0),
            "urls_checked": s.get("urls_checked", 0),
            "last_crawl_at": last.isoformat() if hasattr(last, "isoformat") else None,
        })
    return result


@app.get("/api/admin/users/{user_id}/crawls", tags=["Admin"])
async def admin_user_crawls(user_id: str, admin: User = Depends(get_current_admin)):
    """A specific user's crawl history (most recent first)."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid user ID"})

    target = await User.get(uid)
    if not target:
        return JSONResponse(status_code=404, content={"message": "User not found"})

    jobs = await CrawlJob.find(CrawlJob.user_id == uid).sort("-created_at").limit(100).to_list()
    domain_ids = list({j.domain_id for j in jobs})
    domains = await Domain.find({"_id": {"$in": domain_ids}}).to_list() if domain_ids else []
    dmap = {d.id: d for d in domains}

    return {
        "user": {"id": str(target.id), "email": target.email, "username": target.username},
        "crawls": [{
            "id": str(j.id),
            "domain": dmap.get(j.domain_id).domain if dmap.get(j.domain_id) else "unknown",
            "status": j.status,
            "total_urls_checked": j.total_urls_checked,
            "total_urls_found": j.total_urls_found,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        } for j in jobs],
    }
