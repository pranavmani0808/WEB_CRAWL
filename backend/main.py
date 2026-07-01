from fastapi import FastAPI, Request, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from app.core.config import settings
from app.core.exceptions import CrawlerException
from app.database.database import get_db
from app.models.domain import Domain
from app.models.crawl_job import CrawlJob
from app.models.url import URL
from app.models.crawl_log import CrawlLog
from app.models.user import User
from app.workers.tasks import crawl_domain_task
import uuid
from urllib.parse import urlparse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _cors_headers(request: Request) -> dict:
    """Return CORS headers so error responses aren't blocked by the browser."""
    origin = request.headers.get("origin", "")
    if "*" in origins or origin in origins:
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
async def start_crawl_endpoint(req: CrawlRequest, db: AsyncSession = Depends(get_db)):
    """Start a crawl job for the specified URL"""
    url = req.url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    parsed = urlparse(url)
    domain_name = parsed.netloc or parsed.path.split('/')[0]
    
    # Mock a default user ID for development
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    
    # Ensure default user exists
    user_stmt = select(User).where(User.id == user_id)
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()
    if not user:
        user = User(
            id=user_id,
            email="dev@example.com",
            username="developer",
            password_hash="dev-hash"
        )
        db.add(user)
        await db.flush()

    # Get or create Domain
    stmt = select(Domain).where(Domain.normalized_url == f"{parsed.scheme}://{domain_name}")
    result = await db.execute(stmt)
    domain = result.scalar_one_or_none()
    
    if not domain:
        domain = Domain(
            user_id=user_id,
            original_url=url,
            normalized_url=f"{parsed.scheme}://{domain_name}",
            domain=domain_name,
            status="pending"
        )
        db.add(domain)
        await db.flush()
    
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
    db.add(job)
    await db.commit()
    
    # Dispatch Celery task
    crawl_domain_task.delay(str(job.id))
    
    return {"job_id": str(job.id), "domain_id": str(domain.id)}

@app.get("/api/crawl/jobs", tags=["Crawl"])
async def list_crawl_jobs(db: AsyncSession = Depends(get_db)):
    """List all crawl jobs with associated domains"""
    stmt = select(CrawlJob).options(selectinload(CrawlJob.domain)).order_by(desc(CrawlJob.created_at))
    result = await db.execute(stmt)
    jobs = result.scalars().all()
    return [{
        "id": str(j.id),
        "status": j.status,
        "domain": j.domain.domain,
        "url": j.domain.original_url,
        "total_urls_found": j.total_urls_found,
        "total_urls_checked": j.total_urls_checked,
        "created_at": j.created_at.isoformat()
    } for j in jobs]

@app.get("/api/crawl/jobs/{job_id}", tags=["Crawl"])
async def get_crawl_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Get details, stats and logs for a specific crawl job"""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    stmt = select(CrawlJob).where(CrawlJob.id == job_uuid).options(
        selectinload(CrawlJob.domain),
        selectinload(CrawlJob.statistics)
    )
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()
    
    if not job:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    # Fetch logs
    log_stmt = select(CrawlLog).where(CrawlLog.crawl_job_id == job_uuid).order_by(CrawlLog.timestamp)
    log_res = await db.execute(log_stmt)
    logs = log_res.scalars().all()

    return {
        "id": str(job.id),
        "status": job.status,
        "domain": job.domain.domain,
        "url": job.domain.original_url,
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
            "health_score": job.statistics[0].health_score if job.statistics else None,
            "avg_response_time_ms": job.avg_response_time_ms,
            "speed_urls_per_sec": float(job.crawl_speed_urls_per_sec) if job.crawl_speed_urls_per_sec else 0.0
        } if job.statistics else None,
        "logs": [{
            "timestamp": l.timestamp.isoformat(),
            "level": l.level,
            "message": l.message
        } for l in logs]
    }

@app.get("/api/crawl/jobs/{job_id}/urls", tags=["Crawl"])
async def list_job_urls(job_id: str, db: AsyncSession = Depends(get_db)):
    """List all URLs crawled for a specific job"""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    # Fetch job domain
    stmt = select(CrawlJob.domain_id).where(CrawlJob.id == job_uuid)
    res = await db.execute(stmt)
    domain_id = res.scalar_one_or_none()

    if not domain_id:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    # Fetch URLs
    url_stmt = select(URL).where(URL.domain_id == domain_id).order_by(URL.url)
    url_res = await db.execute(url_stmt)
    urls = url_res.scalars().all()

    return [{
        "id": str(u.id),
        "url": u.url,
        "status_code": u.status_code,
        "status_category": u.status_category,
        "response_time_ms": u.response_time_ms,
        "content_type": u.content_type,
        "canonical_url": u.canonical_url,
        "is_indexable": u.is_indexable,
        "metadata": u.meta_data
    } for u in urls]


@app.post("/api/crawl/jobs/{job_id}/retry", tags=["Crawl"])
async def retry_crawl_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Re-dispatch a stuck or failed crawl job back into the Celery queue."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    stmt = select(CrawlJob).where(CrawlJob.id == job_uuid)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

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
    await db.commit()

    # Re-dispatch Celery task
    crawl_domain_task.delay(str(job.id))
    return {"message": "Job re-dispatched", "job_id": str(job.id)}


@app.post("/api/crawl/jobs/retry-pending", tags=["Crawl"])
async def retry_all_pending_jobs(db: AsyncSession = Depends(get_db)):
    """Re-dispatch all jobs currently stuck in pending state."""
    stmt = select(CrawlJob).where(CrawlJob.status == "pending")
    result = await db.execute(stmt)
    jobs = result.scalars().all()

    dispatched = []
    for job in jobs:
        crawl_domain_task.delay(str(job.id))
        dispatched.append(str(job.id))

    return {"message": f"Re-dispatched {len(dispatched)} jobs", "job_ids": dispatched}


@app.post("/api/crawl/jobs/{job_id}/pause", tags=["Crawl"])
async def pause_crawl_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Pause a running crawl job by marking its status as paused."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    stmt = select(CrawlJob).where(CrawlJob.id == job_uuid)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    if job.status not in ("running", "pending"):
        return JSONResponse(
            status_code=400,
            content={"message": f"Cannot pause a job in '{job.status}' state"}
        )

    job.status = "paused"
    await db.commit()
    return {"message": "Job paused", "job_id": str(job.id)}


@app.post("/api/crawl/jobs/{job_id}/resume", tags=["Crawl"])
async def resume_crawl_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Resume a paused crawl job by re-dispatching it."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    stmt = select(CrawlJob).where(CrawlJob.id == job_uuid)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    if job.status != "paused":
        return JSONResponse(
            status_code=400,
            content={"message": f"Cannot resume a job in '{job.status}' state"}
        )

    job.status = "pending"
    await db.commit()
    crawl_domain_task.delay(str(job.id))
    return {"message": "Job resumed", "job_id": str(job.id)}


@app.delete("/api/crawl/jobs/{job_id}", tags=["Crawl"])
async def delete_crawl_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Permanently delete a crawl job and all associated data."""
    from sqlalchemy import delete as sql_delete
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid job ID format"})

    stmt = select(CrawlJob).where(CrawlJob.id == job_uuid)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        return JSONResponse(status_code=404, content={"message": "Job not found"})

    # Delete associated logs
    await db.execute(sql_delete(CrawlLog).where(CrawlLog.crawl_job_id == job_uuid))
    # Delete the job itself (cascades to statistics if configured)
    await db.delete(job)
    await db.commit()
    return {"message": "Job deleted", "job_id": job_id}

