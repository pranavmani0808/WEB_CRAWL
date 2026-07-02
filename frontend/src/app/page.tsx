"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import axios from "axios";
import {
  Play, RotateCw, Globe,
  Clock, Activity, Check, Server, Terminal, List, Search,
  Pause, Trash2, StopCircle, Download, LogOut, Eye
} from "lucide-react";
import { restoreSession, clearSession, AuthUser } from "@/lib/auth";
import Homepage, { PENDING_URL_KEY } from "@/components/Homepage";
import CrawlingAnimation from "@/components/CrawlingAnimation";
import PageDetailModal from "@/components/PageDetailModal";

// Configure base API url
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface CrawlJob {
  id: string;
  status: string;
  domain: string;
  url: string;
  total_urls_found: number;
  total_urls_checked: number;
  created_at: string;
}

interface JobDetails {
  id: string;
  status: string;
  domain: string;
  url: string;
  started_at: string | null;
  completed_at: string | null;
  stages?: {
    domain_validation: boolean;
    dns_resolution: boolean;
    ssl_verification: boolean;
    robots_found: boolean;
    sitemap_discovery: boolean;
    parsing_indexes: boolean;
    parsing_sitemaps: boolean;
    url_discovery: boolean;
    http_checking: boolean;
  };
  progress: {
    total_sitemaps_found: number;
    total_urls_found: number;
    total_urls_checked: number;
    urls_2xx: number;
    urls_3xx: number;
    urls_4xx: number;
    urls_5xx: number;
    urls_timeout: number;
    urls_dns_error: number;
  };
  stats: {
    health_score: number | null;
    avg_response_time_ms: number | null;
    speed_urls_per_sec: number;
  } | null;
  logs: {
    timestamp: string;
    level: string;
    message: string;
  }[];
}

interface CrawledUrl {
  id: string;
  url: string;
  status_code: number | null;
  status_category: string | null;
  response_time_ms: number | null;
  content_type: string | null;
  canonical_url: string | null;
  is_indexable: boolean | null;
  crawl_status?: string;
  metadata: any;
  seo_issues?: { type: string; category: string; issue: string; details: string }[];
}

export default function Dashboard() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRetryingAll, setIsRetryingAll] = useState(false);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [pausingJobId, setPausingJobId] = useState<string | null>(null);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [jobs, setJobs] = useState<CrawlJob[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobDetails, setJobDetails] = useState<JobDetails | null>(null);
  const [crawledUrls, setCrawledUrls] = useState<CrawledUrl[]>([]);
  const [filterCategory, setFilterCategory] = useState<string>("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedUrl, setSelectedUrl] = useState<CrawledUrl | null>(null);

  // Export audited URLs to CSV
  const downloadCsv = () => {
    if (crawledUrls.length === 0) return;
    const headers = ["URL", "Status Code", "Status Category", "Response Time (ms)", "Content Type", "Canonical URL", "Indexable", "Images Count", "Missing Alt Images"];
    const rows = crawledUrls.map(u => {
      const imagesCount = u.metadata?.images?.length || 0;
      const missingAltCount = u.metadata?.images?.filter((i: any) => !i.alt).length || 0;
      return [
        `"${u.url.replace(/"/g, '""')}"`,
        u.status_code !== null ? u.status_code : "",
        u.status_category || "",
        u.response_time_ms !== null ? u.response_time_ms : "",
        u.content_type || "",
        u.canonical_url ? `"${u.canonical_url.replace(/"/g, '""')}"` : "",
        u.is_indexable === null ? "" : u.is_indexable ? "True" : "False",
        imagesCount,
        missingAltCount
      ];
    });
    
    const csvString = [headers.join(","), ...rows.map(e => e.join(","))].join("\n");
    const blob = new Blob([csvString], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `${jobDetails?.domain || "crawl"}_audit_report.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Load jobs list
  const loadJobs = async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/crawl/jobs`);
      setJobs(res.data);
      if (res.data.length > 0 && !activeJobId) {
        setActiveJobId(res.data[0].id);
      }
    } catch (err) {
      console.error("Failed to load jobs", err);
    }
  };

  // Load active job details
  const loadJobDetails = async (jobId: string) => {
    try {
      const res = await axios.get(`${API_BASE}/api/crawl/jobs/${jobId}`);
      setJobDetails(res.data);

      const urlRes = await axios.get(`${API_BASE}/api/crawl/jobs/${jobId}/urls`);
      setCrawledUrls(urlRes.data);
    } catch (err) {
      console.error("Failed to load job details", err);
    }
  };

  // Retry a specific job
  const retryJob = async (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setRetryingJobId(jobId);
    try {
      await axios.post(`${API_BASE}/api/crawl/jobs/${jobId}/retry`);
      setActiveJobId(jobId);
      await loadJobs();
    } catch (err) {
      console.error("Failed to retry job", err);
    } finally {
      setRetryingJobId(null);
    }
  };

  // Pause a running job
  const pauseJob = async (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setPausingJobId(jobId);
    try {
      await axios.post(`${API_BASE}/api/crawl/jobs/${jobId}/pause`);
      await loadJobs();
      if (activeJobId === jobId) loadJobDetails(jobId);
    } catch (err) {
      console.error("Failed to pause job", err);
    } finally {
      setPausingJobId(null);
    }
  };

  // Resume a paused job
  const resumeJob = async (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setPausingJobId(jobId);
    try {
      await axios.post(`${API_BASE}/api/crawl/jobs/${jobId}/resume`);
      await loadJobs();
      if (activeJobId === jobId) loadJobDetails(jobId);
    } catch (err) {
      console.error("Failed to resume job", err);
    } finally {
      setPausingJobId(null);
    }
  };

  // Delete a job
  const deleteJob = async (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirmDeleteId !== jobId) {
      setConfirmDeleteId(jobId);
      return;
    }
    setDeletingJobId(jobId);
    setConfirmDeleteId(null);
    try {
      await axios.delete(`${API_BASE}/api/crawl/jobs/${jobId}`);
      if (activeJobId === jobId) {
        setActiveJobId(null);
        setJobDetails(null);
        setCrawledUrls([]);
      }
      await loadJobs();
    } catch (err) {
      console.error("Failed to delete job", err);
    } finally {
      setDeletingJobId(null);
    }
  };

  // Retry ALL pending jobs at once
  const retryAllPending = async () => {
    setIsRetryingAll(true);
    try {
      await axios.post(`${API_BASE}/api/crawl/jobs/retry-pending`);
      await loadJobs();
    } catch (err) {
      console.error("Failed to retry all pending jobs", err);
    } finally {
      setIsRetryingAll(false);
    }
  };

  // Restore session on mount; show the marketing homepage if there isn't one.
  useEffect(() => {
    const restored = restoreSession();
    if (!restored) {
      setAuthChecked(true);
      return;
    }
    setUser(restored);
    setAuthChecked(true);

    // Pick up a domain entered on the homepage before signing in.
    const pendingUrl = localStorage.getItem(PENDING_URL_KEY);
    if (pendingUrl) {
      setUrlInput(pendingUrl);
      localStorage.removeItem(PENDING_URL_KEY);
    }

    // If the token expires/becomes invalid mid-session, any request will 401 -
    // catch that globally and send the user back to login.
    const interceptorId = axios.interceptors.response.use(
      (res) => res,
      (err) => {
        if (err?.response?.status === 401) {
          clearSession();
          router.replace("/login");
        }
        return Promise.reject(err);
      }
    );
    return () => axios.interceptors.response.eject(interceptorId);
  }, [router]);

  const handleLogout = () => {
    clearSession();
    router.replace("/login");
  };

  useEffect(() => {
    if (authChecked && user) loadJobs();
  }, [authChecked, user]);

  useEffect(() => {
    if (activeJobId && authChecked && user) {
      loadJobDetails(activeJobId);
      // Always poll while a job is active or pending
      const interval = setInterval(() => {
        loadJobDetails(activeJobId);
        loadJobs();
      }, 3000);
      return () => clearInterval(interval);
    }
  }, [activeJobId]);

  const handleStartCrawl = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!urlInput) return;
    setIsSubmitting(true);
    try {
      const res = await axios.post(`${API_BASE}/api/crawl`, { url: urlInput });
      setUrlInput("");
      setActiveJobId(res.data.job_id);
      await loadJobs();
    } catch (err) {
      alert("Failed to start crawl job. Make sure the backend server and Celery are running.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "completed": return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
      case "running": return "bg-blue-500/10 text-blue-400 border-blue-500/20 animate-pulse";
      case "failed": return "bg-red-500/10 text-red-400 border-red-500/20";
      case "paused": return "bg-amber-500/10 text-amber-400 border-amber-500/20";
      default: return "bg-slate-500/10 text-slate-400 border-slate-500/20";
    }
  };

  const hasPendingJobs = jobs.some(j => j.status === "pending" || j.status === "failed");

  const filteredUrls = crawledUrls.filter(u => {
    const matchesSearch = u.url.toLowerCase().includes(searchTerm.toLowerCase());
    if (filterCategory === "all") return matchesSearch;
    if (filterCategory === "success") return (u.status_category === "success" || (u.status_code && u.status_code >= 200 && u.status_code < 300)) && matchesSearch;
    if (filterCategory === "3xx") return (u.status_category === "redirect" || (u.status_code && u.status_code >= 300 && u.status_code < 400)) && matchesSearch;
    if (filterCategory === "4xx") return (u.status_category === "client_error" || (u.status_code && u.status_code >= 400 && u.status_code < 500)) && matchesSearch;
    if (filterCategory === "5xx") return (u.status_category === "server_error" || (u.status_code && u.status_code >= 500)) && matchesSearch;
    if (filterCategory === "error") return (u.status_category === "client_error" || u.status_category === "server_error" || u.status_category === "timeout" || u.status_category === "dns_error" || (u.status_code && u.status_code >= 400)) && matchesSearch;
    return matchesSearch;
  });

  if (!authChecked) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950 text-slate-400">
        Loading...
      </div>
    );
  }

  if (!user) {
    return <Homepage />;
  }

  return (
    <div className="flex h-full min-h-screen flex-col bg-slate-950 text-slate-100 font-sans">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-slate-900 bg-slate-900/50 px-6 py-4 backdrop-blur">
        <div className="flex items-center space-x-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 shadow-lg shadow-indigo-500/20">
            <Globe className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white">Popz AI Crawl</h1>
            <p className="text-xs text-slate-400">Sitemap-Based Domain Inventory Auditing</p>
          </div>
        </div>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <span className="flex h-2 w-2 rounded-full bg-emerald-500"></span>
            <span className="text-xs font-medium text-slate-400">Backend Connected</span>
          </div>
          {user && (
            <div className="flex items-center space-x-3 border-l border-slate-800 pl-4">
              <span className="text-xs font-medium text-slate-300">{user.username}</span>
              <button
                onClick={handleLogout}
                className="flex items-center space-x-1 rounded-lg border border-slate-800 px-2 py-1 text-xs text-slate-400 transition hover:border-red-500/30 hover:text-red-400"
                title="Log out"
              >
                <LogOut className="h-3.5 w-3.5" />
                <span>Log out</span>
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar: Crawl Jobs List */}
        <aside className="w-80 border-r border-slate-900 bg-slate-900/20 p-6 flex flex-col space-y-6 overflow-y-auto">
          {/* Crawl Trigger Form */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-5 space-y-4">
            <div>
              <h2 className="text-lg font-bold text-white">Add your domain</h2>
              <p className="mt-1 text-xs text-slate-400">Enter a domain address to get started.</p>
            </div>
            <form onSubmit={handleStartCrawl} className="space-y-3">
              <div className="relative">
                <Globe className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                <input
                  type="text"
                  placeholder="https://example.com"
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  disabled={isSubmitting}
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 py-3 pl-10 pr-3 text-sm text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <button
                type="submit"
                disabled={isSubmitting}
                className="flex w-full items-center justify-center space-x-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-md shadow-indigo-600/20 transition hover:bg-indigo-500 focus:outline-none disabled:opacity-50"
              >
                {isSubmitting ? (
                  <RotateCw className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <Play className="h-4 w-4 fill-current" />
                    <span>Start Audit</span>
                  </>
                )}
              </button>
            </form>
          </div>

          <hr className="border-slate-900" />

          {/* Retry-all banner for stuck jobs */}
          {hasPendingJobs && (
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2.5 flex items-center justify-between">
              <div className="text-xs text-amber-400">
                <span className="font-semibold">Jobs stuck?</span> Re-queue all
              </div>
              <button
                onClick={retryAllPending}
                disabled={isRetryingAll}
                className="flex items-center gap-1 text-[11px] font-semibold text-amber-400 hover:text-amber-300 disabled:opacity-50"
              >
                {isRetryingAll ? (
                  <RotateCw className="h-3 w-3 animate-spin" />
                ) : (
                  <RotateCw className="h-3 w-3" />
                )}
                Retry All
              </button>
            </div>
          )}

          {/* Job History */}
          <div className="flex-1 flex flex-col space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Crawl Jobs History</h2>
              <button onClick={loadJobs} className="text-slate-400 hover:text-white">
                <RotateCw className="h-3.5 w-3.5" />
              </button>
            </div>

            <div className="flex-1 space-y-2 overflow-y-auto pr-1">
              {jobs.map((j) => (
                <div
                  key={j.id}
                  onClick={() => { setActiveJobId(j.id); setConfirmDeleteId(null); }}
                  className={`group w-full text-left p-3 rounded-lg border transition cursor-pointer relative ${
                    activeJobId === j.id
                      ? "bg-slate-900 border-slate-800 text-white"
                      : "bg-slate-900/40 border-transparent hover:bg-slate-900/60 text-slate-300"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-sm truncate max-w-[110px]">{j.domain}</span>
                    <div className="flex items-center gap-1">
                      {/* Retry button for pending/failed, and for running - a job can get
                          orphaned (stuck at "running" forever) if the backend worker
                          restarts mid-crawl, and this is the only way to recover it. */}
                      {(j.status === "pending" || j.status === "failed" || j.status === "running") && (
                        <button
                          onClick={(e) => retryJob(j.id, e)}
                          disabled={retryingJobId === j.id}
                          title="Re-dispatch this job"
                          className={`text-slate-500 hover:text-indigo-400 transition disabled:opacity-40 p-0.5 rounded ${
                            j.status === "running" ? "opacity-0 group-hover:opacity-100" : ""
                          }`}
                        >
                          <RotateCw className={`h-3 w-3 ${retryingJobId === j.id ? "animate-spin" : ""}`} />
                        </button>
                      )}
                      {/* Pause button for running/pending */}
                      {(j.status === "running" || j.status === "pending") && (
                        <button
                          onClick={(e) => pauseJob(j.id, e)}
                          disabled={pausingJobId === j.id}
                          title="Pause this job"
                          className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-amber-400 transition-all disabled:opacity-40 p-0.5 rounded"
                        >
                          {pausingJobId === j.id
                            ? <RotateCw className="h-3 w-3 animate-spin" />
                            : <Pause className="h-3 w-3" />}
                        </button>
                      )}
                      {/* Resume button for paused */}
                      {j.status === "paused" && (
                        <button
                          onClick={(e) => resumeJob(j.id, e)}
                          disabled={pausingJobId === j.id}
                          title="Resume this job"
                          className="text-amber-500 hover:text-emerald-400 transition disabled:opacity-40 p-0.5 rounded"
                        >
                          {pausingJobId === j.id
                            ? <RotateCw className="h-3 w-3 animate-spin" />
                            : <Play className="h-3 w-3 fill-current" />}
                        </button>
                      )}
                      {/* Delete button — first click shows red confirm, second click deletes */}
                      <button
                        onClick={(e) => deleteJob(j.id, e)}
                        disabled={deletingJobId === j.id}
                        title={confirmDeleteId === j.id ? "Click again to confirm delete" : "Delete this job"}
                        className={`transition-all p-0.5 rounded disabled:opacity-40 ${
                          confirmDeleteId === j.id
                            ? "opacity-100 text-red-400 animate-pulse"
                            : "opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400"
                        }`}
                      >
                        {deletingJobId === j.id
                          ? <RotateCw className="h-3 w-3 animate-spin" />
                          : confirmDeleteId === j.id
                          ? <StopCircle className="h-3 w-3" />
                          : <Trash2 className="h-3 w-3" />}
                      </button>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${getStatusColor(j.status)}`}>
                        {j.status}
                      </span>
                    </div>
                  </div>
                  <div className="mt-1 flex items-center justify-between text-xs text-slate-500">
                    <span>{j.total_urls_checked} / {j.total_urls_found} URLs</span>
                    <span>{new Date(j.created_at).toLocaleDateString()}</span>
                  </div>
                  {/* Confirm delete hint */}
                  {confirmDeleteId === j.id && (
                    <div className="mt-1.5 text-[10px] text-red-400/80 font-medium">
                      ⚠ Click delete again to confirm
                    </div>
                  )}
                </div>
              ))}
              {jobs.length === 0 && (
                <div className="text-center py-6 text-sm text-slate-500">No crawl jobs found yet.</div>
              )}
            </div>
          </div>
        </aside>

        {/* Dashboard Panels */}
        <main className="flex-1 p-8 overflow-y-auto space-y-8">
          {jobDetails ? (
            <>
              {/* Job summary section */}
              <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-slate-900 pb-6 gap-4">
                <div>
                  <div className="flex items-center space-x-3">
                    <h2 className="text-2xl font-bold text-white tracking-tight">{jobDetails.domain}</h2>
                    <span className={`text-xs px-2.5 py-0.5 rounded-full border ${getStatusColor(jobDetails.status)}`}>
                      {jobDetails.status}
                    </span>
                  </div>
                  <p className="text-sm text-slate-400 mt-1">Audit URL: <a href={jobDetails.url} target="_blank" rel="noreferrer" className="text-indigo-400 hover:underline">{jobDetails.url}</a></p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="bg-slate-900 border border-slate-800 p-3 rounded-xl flex items-center gap-3">
                    <Clock className="h-5 w-5 text-indigo-400" />
                    <div>
                      <div className="text-xs text-slate-400">Duration</div>
                      <div className="text-sm font-semibold text-white">
                        {jobDetails.started_at ? (
                           jobDetails.completed_at ? (
                             `${Math.round((new Date(jobDetails.completed_at).getTime() - new Date(jobDetails.started_at).getTime()) / 1000)}s`
                           ) : "Running..."
                        ) : "-"}
                      </div>
                    </div>
                  </div>
                  <div className="bg-slate-900 border border-slate-800 p-3 rounded-xl flex items-center gap-3">
                    <Activity className="h-5 w-5 text-indigo-400" />
                    <div>
                      <div className="text-xs text-slate-400">Speed</div>
                      <div className="text-sm font-semibold text-white">
                        {jobDetails.stats?.speed_urls_per_sec || 0} req/s
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Live crawling animation - shown while actively fetching pages */}
              {(jobDetails.status === "running" || jobDetails.status === "pending") && (
                <CrawlingAnimation
                  domain={jobDetails.domain}
                  urlsChecked={jobDetails.progress.total_urls_checked}
                  urlsFound={jobDetails.progress.total_urls_found}
                  percent={
                    Math.max(jobDetails.progress.total_urls_found, jobDetails.progress.total_urls_checked) > 0
                      ? Math.round((jobDetails.progress.total_urls_checked / Math.max(jobDetails.progress.total_urls_found, jobDetails.progress.total_urls_checked)) * 100)
                      : 0
                  }
                />
              )}

              {/* Interactive Live Pipeline Stepper */}
              <div className="bg-slate-900/30 border border-slate-900/80 p-6 rounded-2xl backdrop-blur-sm space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <Activity className="h-4 w-4 text-indigo-400 animate-pulse" />
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">Live Audit Pipeline Stages</h3>
                  </div>
                  {jobDetails.status === "running" && (
                    <span className="flex items-center space-x-1.5 bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded-full text-[10px] font-medium border border-blue-500/20 animate-pulse">
                      <span className="h-1.5 w-1.5 bg-blue-400 rounded-full"></span>
                      <span>Crawling Live</span>
                    </span>
                  )}
                </div>

                <div className="relative flex flex-col md:flex-row justify-between items-start md:items-center gap-4 pt-2">
                  {[
                    { key: "domain_validation" as const, label: "Domain Check", desc: "Verifying domain status" },
                    { key: "dns_resolution" as const, label: "DNS Resolution", desc: "Resolving IP address" },
                    { key: "ssl_verification" as const, label: "SSL Audit", desc: "Validating SSL certificate" },
                    { key: "robots_found" as const, label: "Robots.txt", desc: "Checking robots exclusions" },
                    { key: "sitemap_discovery" as const, label: "Sitemap Finder", desc: "Discovering sitemaps" },
                    { key: "parsing_indexes" as const, label: "Parse Indexes", desc: "Reading sitemap indexes" },
                    { key: "parsing_sitemaps" as const, label: "Parse Sitemaps", desc: "Extracting XML URLs" },
                    { key: "url_discovery" as const, label: "URL Extraction", desc: "Consolidating unique URLs" },
                    { key: "http_checking" as const, label: "Crawling", desc: "Auditing page responses" },
                  ].map((stage, idx, arr) => {
                    const status = (() => {
                      if (!jobDetails.stages) return "pending";
                      const isCurrentTrue = jobDetails.stages[stage.key];
                      if (!isCurrentTrue) return "pending";
                      if (jobDetails.status === "completed") return "completed";
                      if (jobDetails.status === "failed") return "failed";
                      const nextStageTrue = arr.slice(idx + 1).some(s => jobDetails.stages?.[s.key]);
                      if (nextStageTrue) return "completed";
                      return "active";
                    })();

                    return (
                      <div key={stage.key} className="flex-1 w-full flex md:flex-col items-center md:text-center relative group">
                        {/* Connecting Line */}
                        {idx < arr.length - 1 && (
                          <div className="hidden md:block absolute left-[50%] right-[-50%] top-4 h-[2px] bg-slate-900 group-hover:bg-slate-800 transition-colors z-0">
                            <div 
                              className={`h-full transition-all duration-500 ${
                                status === "completed" ? "bg-indigo-500" :
                                status === "active" ? "bg-indigo-500/50 animate-pulse" : "bg-transparent"
                              }`}
                            />
                          </div>
                        )}

                        {/* Node Bubble */}
                        <div className="relative z-10 flex items-center justify-center shrink-0">
                          <div 
                            className={`h-8 w-8 rounded-full border flex items-center justify-center transition-all duration-300 ${
                              status === "completed" ? "bg-indigo-600/20 border-indigo-500 text-indigo-400 shadow-lg shadow-indigo-500/10" :
                              status === "active" ? "bg-blue-600/20 border-blue-400 text-blue-300 animate-pulse shadow-md shadow-blue-500/20" :
                              status === "failed" ? "bg-red-600/20 border-red-500 text-red-400" :
                              "bg-slate-900 border-slate-800 text-slate-500"
                            }`}
                          >
                            {status === "completed" ? (
                              <Check className="h-4 w-4" />
                            ) : status === "active" ? (
                              <RotateCw className="h-4 w-4 animate-spin" />
                            ) : (
                              <span className="text-xs font-semibold">{idx + 1}</span>
                            )}
                          </div>
                        </div>

                        {/* Text Label */}
                        <div className="ml-4 md:ml-0 md:mt-3 flex flex-col md:items-center">
                          <span className={`text-xs font-semibold transition-colors duration-300 ${
                            status === "completed" ? "text-slate-200" :
                            status === "active" ? "text-blue-400" : "text-slate-500"
                          }`}>
                            {stage.label}
                          </span>
                          <span className="text-[10px] text-slate-500 hidden md:block mt-0.5 max-w-[90px] leading-tight">
                            {stage.desc}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Grid: Metrics and Status Breakdown - only meaningful once the
                  crawl has actually finished; mid-crawl these are all
                  0/partial and just look broken. */}
              {jobDetails.status === "completed" && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Progress Card */}
                <div className="bg-slate-900/50 border border-slate-900 p-6 rounded-2xl flex flex-col justify-between">
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Crawl Progress</h3>
                    <div className="text-3xl font-extrabold text-white mt-2">
                      {jobDetails.progress.total_urls_checked} <span className="text-lg text-slate-500 font-normal">/ {Math.max(jobDetails.progress.total_urls_found, jobDetails.progress.total_urls_checked)} URLs</span>
                    </div>
                  </div>
                  <div className="mt-4">
                    <div className="w-full bg-slate-850 h-2 rounded-full overflow-hidden">
                      <div
                        className="bg-indigo-500 h-full rounded-full transition-all duration-300"
                        style={{
                          width: `${
                            Math.max(jobDetails.progress.total_urls_found, jobDetails.progress.total_urls_checked) > 0
                              ? (jobDetails.progress.total_urls_checked / Math.max(jobDetails.progress.total_urls_found, jobDetails.progress.total_urls_checked)) * 100
                              : 0
                          }%`,
                        }}
                      ></div>
                    </div>
                    <div className="flex justify-between text-xs text-slate-500 mt-2">
                      <span>Sitemaps Found: {jobDetails.progress.total_sitemaps_found}</span>
                      <span>{Math.max(jobDetails.progress.total_urls_found, jobDetails.progress.total_urls_checked) > 0 ? Math.round((jobDetails.progress.total_urls_checked / Math.max(jobDetails.progress.total_urls_found, jobDetails.progress.total_urls_checked)) * 100) : 0}%</span>
                    </div>
                  </div>
                </div>

                {/* Response Code breakdowns */}
                <div className="bg-slate-900/50 border border-slate-900 p-6 rounded-2xl md:col-span-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Response Status Distribution</h3>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-4">
                    <div className="bg-slate-950 p-3 rounded-xl border border-slate-900">
                      <div className="text-emerald-400 text-xl font-bold">{jobDetails.progress.urls_2xx}</div>
                      <div className="text-xs text-slate-400 mt-1">2xx Success</div>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-xl border border-slate-900">
                      <div className="text-blue-400 text-xl font-bold">{jobDetails.progress.urls_3xx}</div>
                      <div className="text-xs text-slate-400 mt-1">3xx Redirects</div>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-xl border border-slate-900">
                      <div className="text-amber-400 text-xl font-bold">{jobDetails.progress.urls_4xx}</div>
                      <div className="text-xs text-slate-400 mt-1">4xx Client Errors</div>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-xl border border-slate-900">
                      <div className="text-red-400 text-xl font-bold">{jobDetails.progress.urls_5xx + jobDetails.progress.urls_timeout + jobDetails.progress.urls_dns_error}</div>
                      <div className="text-xs text-slate-400 mt-1">Failed/Broken</div>
                    </div>
                  </div>
                </div>
              </div>
              )}

              {/* Grid: Console Logs & URL Table - the URL table only appears
                  once the crawl is done; the activity log stays visible the
                  whole time and just takes the full row until then. */}
              <div className={`grid grid-cols-1 ${jobDetails.status === "completed" ? "lg:grid-cols-3" : ""} gap-8`}>
                {/* Real-time Activity Terminal */}
                <div className="bg-slate-900/50 border border-slate-900 rounded-2xl flex flex-col h-96 overflow-hidden">
                  <div className="border-b border-slate-900 px-4 py-3 bg-slate-900/30 flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <Terminal className="h-4 w-4 text-indigo-400" />
                      <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Activity Log Console</span>
                    </div>
                    <span className="flex h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse"></span>
                  </div>
                  <div className="flex-1 p-4 font-mono text-[11px] text-slate-300 overflow-y-auto space-y-2.5">
                    {jobDetails.logs.map((l, idx) => (
                      <div key={idx} className="flex gap-2.5 items-start leading-relaxed border-b border-slate-900/50 pb-1.5">
                        <span className="text-slate-500 shrink-0">{new Date(l.timestamp).toLocaleTimeString()}</span>
                        <span className={`font-semibold shrink-0 uppercase ${l.level === "error" ? "text-red-400" : l.level === "warning" ? "text-amber-400" : "text-blue-400"}`}>
                          [{l.level}]
                        </span>
                        <span>{l.message}</span>
                      </div>
                    ))}
                    {jobDetails.logs.length === 0 && (
                      <div className="text-slate-500 text-center py-12">Waiting for crawler logs...</div>
                    )}
                  </div>
                </div>

                {/* Audited URLs List - only after a successful crawl */}
                {jobDetails.status === "completed" && (
                <div className="lg:col-span-2 bg-slate-900/50 border border-slate-900 rounded-2xl flex flex-col h-96 overflow-hidden">
                  {/* Filter Toolbar */}
                  <div className="border-b border-slate-900 px-6 py-4 bg-slate-900/30 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                    <div className="flex items-center space-x-2">
                      <List className="h-4 w-4 text-indigo-400" />
                      <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Audited Sitemap URLs</span>
                    </div>
                    
                    <div className="flex items-center space-x-2">
                      <div className="relative">
                        <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-500" />
                        <input
                          type="text"
                          placeholder="Search URL..."
                          value={searchTerm}
                          onChange={(e) => setSearchTerm(e.target.value)}
                          className="pl-8 pr-3 py-1.5 rounded-lg border border-slate-800 bg-slate-950 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                        />
                      </div>
                      <select
                        value={filterCategory}
                        onChange={(e) => setFilterCategory(e.target.value)}
                        className="rounded-lg border border-slate-800 bg-slate-950 px-2 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                      >
                        <option value="all">All Statuses</option>
                        <option value="success">Success (2xx)</option>
                        <option value="3xx">Redirects (3xx)</option>
                        <option value="4xx">Client Errors (4xx)</option>
                        <option value="5xx">Server Errors (5xx)</option>
                        <option value="error">All Errors/Failures</option>
                      </select>
                      <button
                        onClick={downloadCsv}
                        className="flex items-center space-x-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 px-3 py-1.5 text-xs font-semibold text-white transition focus:outline-none"
                        title="Download CSV report"
                      >
                        <Download className="h-3.5 w-3.5" />
                        <span>Download CSV</span>
                      </button>
                    </div>
                  </div>

                  {/* URLs List Container */}
                  <div className="flex-1 overflow-auto">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="border-b border-slate-900 bg-slate-900/20 text-xs font-medium text-slate-400">
                          <th className="px-6 py-3">Audited URL</th>
                          <th className="px-6 py-3">Status</th>
                          <th className="px-6 py-3">Time</th>
                          <th className="px-6 py-3">Type</th>
                          <th className="px-6 py-3"></th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-900 text-xs text-slate-300">
                        {filteredUrls.map((u) => {
                          return (
                            <tr key={u.id} className="hover:bg-slate-900/20 transition">
                              <td className="px-6 py-3.5 font-medium text-white max-w-sm truncate" title={u.url}>
                                {u.url}
                              </td>
                              <td className="px-6 py-3.5">
                                {u.crawl_status === "pending" ? (
                                  <span className="px-2 py-0.5 rounded font-mono bg-slate-800 text-slate-400 border border-slate-700/50">
                                    Pending
                                  </span>
                                ) : u.crawl_status === "checking" ? (
                                  <span className="px-2 py-0.5 rounded font-mono bg-blue-500/10 text-blue-400 border border-blue-500/20 animate-pulse">
                                    Checking...
                                  </span>
                                ) : (
                                  <span className={`px-2 py-0.5 rounded font-mono ${
                                    u.status_code && u.status_code < 300 ? "bg-emerald-500/10 text-emerald-400" :
                                    u.status_code && u.status_code < 400 ? "bg-blue-500/10 text-blue-400" :
                                    "bg-red-500/10 text-red-400"
                                  }`}>
                                    {u.status_code || (u.crawl_status === "failed" ? "Fail" : "Pending")}
                                  </span>
                                )}
                              </td>
                              <td className="px-6 py-3.5 font-mono text-slate-400">
                                {u.response_time_ms ? `${u.response_time_ms}ms` : "-"}
                              </td>
                              <td className="px-6 py-3.5 text-slate-400">
                                {u.content_type || "-"}
                              </td>
                              <td className="px-6 py-3.5">
                                {u.crawl_status === "checked" && (
                                  <button
                                    onClick={() => setSelectedUrl(u)}
                                    title="View page content"
                                    className="flex items-center gap-1 rounded-lg border border-slate-800 px-2 py-1 text-[11px] text-slate-400 transition hover:border-indigo-500/40 hover:text-indigo-400"
                                  >
                                    <Eye className="h-3 w-3" /> View
                                  </button>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                        {filteredUrls.length === 0 && (
                          <tr>
                            <td colSpan={5} className="text-center py-12 text-slate-500">No audited URLs match filters.</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center py-24 text-slate-500 space-y-4">
              <div className="h-16 w-16 bg-slate-900 border border-slate-800 rounded-2xl flex items-center justify-center text-slate-400 shadow-xl">
                <Server className="h-8 w-8" />
              </div>
              <div className="text-center">
                <h3 className="text-lg font-bold text-white">No Active Job Loaded</h3>
                <p className="text-sm mt-1">Select an existing crawl job from the history or start a new audit scan.</p>
              </div>
            </div>
          )}
        </main>
      </div>

      {selectedUrl && <PageDetailModal page={selectedUrl} onClose={() => setSelectedUrl(null)} />}
    </div>
  );
}
