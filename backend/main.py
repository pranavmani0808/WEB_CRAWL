from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from app.core.config import settings
from app.core.exceptions import CrawlerException
from app.database.database import init_db, close_db
from app.models.domain import Domain
from app.models.crawl_job import CrawlJob
from app.models.url import URL
from app.models.crawl_log import CrawlLog
from app.models.user import User
from app.workers.tasks import crawl_domain_task
import uuid
from urllib.parse import urlparse
from pydantic import BaseModel

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

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
    # Log the exception here in production
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

class CrawlRequest(BaseModel):
    url: str

@app.post("/api/crawl", tags=["Crawl"])
async def start_crawl_endpoint(req: CrawlRequest):
    """Start a crawl job for the specified URL"""
    url = req.url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    parsed = urlparse(url)
    domain_name = parsed.netloc or parsed.path.split('/')[0]

    # Mock a default user ID for development
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")

    # Ensure default user exists
    user = await User.find_one(User.id == user_id)
    if not user:
        user = User(
            id=user_id,
            email="dev@example.com",
            username="developer",
            password_hash="dev-hash"
        )
        await user.insert()

    # Get or create Domain
    normalized_url = f"{parsed.scheme}://{domain_name}"
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
async def list_crawl_jobs():
    """List all crawl jobs with associated domains"""
    jobs = await CrawlJob.find().sort("created_at", -1).to_list(None)

    result = []
    for j in jobs:
        domain = await Domain.get(j.domain_id)
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
async def get_crawl_job(job_id: str):
    """Get details, stats and logs for a specific crawl job"""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    job = await CrawlJob.get(job_uuid)

    if not job:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    # Fetch domain
    domain = await Domain.get(job.domain_id)

    # Fetch logs
    logs = await CrawlLog.find(CrawlLog.crawl_job_id == job_uuid).sort("timestamp", 1).to_list(None)

    # Fetch statistics
    stats = await CrawlStatistics.find_one(CrawlStatistics.crawl_job_id == job_uuid)

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
async def list_job_urls(job_id: str):
    """List all URLs crawled for a specific job"""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    # Fetch job
    job = await CrawlJob.get(job_uuid)
    if not job:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    # Fetch URLs for this domain
    urls = await URL.find(URL.domain_id == job.domain_id).sort("url", 1).to_list(None)

    return [{
        "id": str(u.id),
        "url": u.url,
        "status_code": u.status_code,
        "status_category": u.status_category,
        "response_time_ms": u.response_time_ms,
        "content_type": u.content_type,
        "canonical_url": u.canonical_url,
        "is_indexable": u.is_indexable,
        "crawl_status": u.crawl_status,
        "metadata": u.meta_data
    } for u in urls]


@app.post("/api/crawl/jobs/{job_id}/retry", tags=["Crawl"])
async def retry_crawl_job(job_id: str):
    """Re-dispatch a stuck or failed crawl job back into the Celery queue."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    job = await CrawlJob.get(job_uuid)

    if not job:
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
    job.started_at = None
    job.completed_at = None
    await job.save()

    # Re-dispatch Celery task
    crawl_domain_task.delay(str(job.id))
    return {"message": "Job re-dispatched", "job_id": str(job.id)}


@app.post("/api/crawl/jobs/retry-pending", tags=["Crawl"])
async def retry_all_pending_jobs():
    """Re-dispatch all jobs currently stuck in pending state."""
    jobs = await CrawlJob.find(CrawlJob.status == "pending").to_list(None)

    dispatched = []
    for job in jobs:
        crawl_domain_task.delay(str(job.id))
        dispatched.append(str(job.id))

    return {"message": f"Re-dispatched {len(dispatched)} jobs", "job_ids": dispatched}


@app.post("/api/crawl/jobs/{job_id}/pause", tags=["Crawl"])
async def pause_crawl_job(job_id: str):
    """Pause a running crawl job by marking its status as paused."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    job = await CrawlJob.get(job_uuid)

    if not job:
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
async def resume_crawl_job(job_id: str):
    """Resume a paused crawl job by re-dispatching it."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    job = await CrawlJob.get(job_uuid)

    if not job:
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


@app.delete("/api/crawl/jobs/{job_id}", tags=["Crawl"])
async def delete_crawl_job(job_id: str):
    """Permanently delete a crawl job and all associated data."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    job = await CrawlJob.get(job_uuid)

    if not job:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    # Delete associated logs
    await CrawlLog.delete_many(CrawlLog.crawl_job_id == job_uuid)
    # Delete the job itself
    await job.delete()
    return {"message": "Job deleted", "job_id": job_id}

