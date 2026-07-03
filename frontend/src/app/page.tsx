"use client";

import React, { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import axios from "axios";
import {
  Play, RotateCw, Globe,
  Clock, Activity, Check, Terminal, List, Search,
  Download, LogOut, Eye, Gauge, BarChart3, Sparkles, History, Square, Trash2, FileText
} from "lucide-react";
import { restoreSession, clearSession, AuthUser } from "@/lib/auth";
import Homepage, { PENDING_URL_KEY } from "@/components/Homepage";
import CrawlingAnimation from "@/components/CrawlingAnimation";
import PageDetailModal from "@/components/PageDetailModal";
import AuditPreviewCard from "@/components/AuditPreviewCard";

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
  const [isCancelling, setIsCancelling] = useState(false);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [isDownloadingPdf, setIsDownloadingPdf] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [jobs, setJobs] = useState<CrawlJob[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobDetails, setJobDetails] = useState<JobDetails | null>(null);
  const [crawledUrls, setCrawledUrls] = useState<CrawledUrl[]>([]);
  const [filterCategory, setFilterCategory] = useState<string>("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedUrl, setSelectedUrl] = useState<CrawledUrl | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [historyPos, setHistoryPos] = useState<{ top: number; left: number } | null>(null);
  const HISTORY_PANEL_WIDTH = 320; // matches the panel's w-80
  const historyBtnRef = useRef<HTMLButtonElement>(null);

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

  // Download the server-generated PDF audit report
  const downloadPdf = async () => {
    if (!jobDetails) return;
    setIsDownloadingPdf(true);
    try {
      const res = await axios.get(`${API_BASE}/api/crawl/jobs/${jobDetails.id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const link = document.createElement("a");
      link.setAttribute("href", url);
      link.setAttribute("download", `${jobDetails.domain}_audit_report.pdf`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Failed to download PDF report", err);
      alert("Failed to generate PDF report.");
    } finally {
      setIsDownloadingPdf(false);
    }
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

  // Ask a running/pending job to stop. This just flips the job to "stopping" -
  // the backend engine notices within a few seconds and settles it into
  // "cancelled" once the in-flight requests are actually torn down.
  const cancelCrawl = async (jobId: string) => {
    setIsCancelling(true);
    try {
      await axios.post(`${API_BASE}/api/crawl/jobs/${jobId}/cancel`);
      await loadJobDetails(jobId);
      await loadJobs();
    } catch (err) {
      console.error("Failed to cancel crawl job", err);
    } finally {
      setIsCancelling(false);
    }
  };

  // Delete a job - first click arms a confirmation, second click actually deletes.
  const deleteJob = async (jobId: string) => {
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

  // Keep the job list (and therefore the Active Crawls switcher) fresh
  // whenever anything is actually running/pending, independent of whichever
  // single job's full detail view happens to be open below - this is what
  // lets you start a second crawl and see both progressing at once.
  const hasLiveJobs = jobs.some(j => j.status === "running" || j.status === "pending");
  useEffect(() => {
    if (!(authChecked && user && hasLiveJobs)) return;
    const interval = setInterval(loadJobs, 3000);
    return () => clearInterval(interval);
  }, [authChecked, user, hasLiveJobs]);

  // Poll the full detail view (including the potentially large audited-URL
  // list) only while the currently-viewed job itself is still active - once
  // it's completed/failed/cancelled the data is final, so continuing to
  // re-fetch and re-render a large URL table every 3s was pure wasted work
  // and a real source of UI jank on big crawls.
  useEffect(() => {
    if (!(activeJobId && authChecked && user)) return;
    loadJobDetails(activeJobId);
    const isTerminal = jobDetails && jobDetails.id === activeJobId &&
      ["completed", "failed", "cancelled"].includes(jobDetails.status);
    if (isTerminal) return;
    const interval = setInterval(() => loadJobDetails(activeJobId), 3000);
    return () => clearInterval(interval);
  }, [activeJobId, jobDetails?.status]);

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
      case "stopping": return "bg-amber-500/10 text-amber-400 border-amber-500/20 animate-pulse";
      case "cancelled": return "bg-slate-500/10 text-slate-400 border-slate-500/20";
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
      <header className="relative flex items-center justify-between gap-3 border-b border-slate-900 bg-slate-900/40 px-4 py-3 backdrop-blur-xl sm:px-6 sm:py-4">
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-indigo-500/40 to-transparent" />
        <div className="flex min-w-0 items-center space-x-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 shadow-lg shadow-indigo-500/25 sm:h-10 sm:w-10">
            <Globe className="h-4.5 w-4.5 text-white sm:h-5 sm:w-5" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-base font-bold tracking-tight text-white sm:text-lg">Popz AI Crawl</h1>
            <p className="hidden truncate text-xs text-slate-400 sm:block">Sitemap-Based Domain Inventory Auditing</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center space-x-2 sm:space-x-4">
          <div className="flex items-center space-x-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 sm:px-3">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
            </span>
            <span className="hidden text-xs font-medium text-emerald-400 sm:inline">Backend Connected</span>
          </div>
          {user && (
            <div className="flex items-center space-x-2 border-l border-slate-800 pl-2 sm:space-x-3 sm:pl-4">
              <div className="relative">
                <button
                  ref={historyBtnRef}
                  onClick={() => {
                    if (!showHistory && historyBtnRef.current) {
                      const rect = historyBtnRef.current.getBoundingClientRect();
                      // Right-align the panel's right edge with the button's, then
                      // clamp so it can never spill past either screen edge on
                      // narrow viewports (a right-anchored CSS "right" offset alone
                      // isn't enough - it can still push the left edge negative).
                      const desiredLeft = rect.right - HISTORY_PANEL_WIDTH;
                      const clampedLeft = Math.max(8, Math.min(desiredLeft, window.innerWidth - HISTORY_PANEL_WIDTH - 8));
                      setHistoryPos({ top: rect.bottom + 8, left: clampedLeft });
                    }
                    setShowHistory((v) => !v);
                  }}
                  title="View past crawls"
                  className={`flex items-center justify-center rounded-lg border p-1.5 transition ${
                    showHistory
                      ? "border-indigo-500/40 bg-indigo-500/10 text-indigo-400"
                      : "border-slate-800 text-slate-400 hover:border-indigo-500/40 hover:text-indigo-400"
                  }`}
                >
                  <History className="h-4 w-4" />
                </button>
                {showHistory && historyPos && typeof document !== "undefined" && createPortal(
                  <>
                    {/* Rendered via portal at document.body - the header's backdrop-blur
                        creates its own stacking context, which trapped this dropdown
                        underneath later page content (e.g. the New Audit bar) despite
                        a high z-index, since z-index only competes within the same
                        stacking context. */}
                    <div className="fixed inset-0 z-[100] bg-black/30" onClick={() => setShowHistory(false)} />
                    <div
                      style={{ position: "fixed", top: historyPos.top, left: historyPos.left }}
                      className="z-[101] w-80 max-w-[calc(100vw-2rem)] max-h-96 overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 shadow-2xl shadow-black/60"
                    >
                      <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900 px-4 py-3">
                        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Past Crawls</span>
                        <button onClick={loadJobs} className="text-slate-500 transition hover:text-white" title="Refresh">
                          <RotateCw className="h-3.5 w-3.5" />
                        </button>
                      </div>
                      <div className="space-y-1 bg-slate-900 p-2">
                        {jobs.map((j) => (
                          <div
                            key={j.id}
                            role="button"
                            tabIndex={0}
                            onClick={() => { setActiveJobId(j.id); setShowHistory(false); }}
                            onKeyDown={(e) => { if (e.key === "Enter") { setActiveJobId(j.id); setShowHistory(false); } }}
                            className={`group relative w-full cursor-pointer rounded-lg p-2.5 text-left transition ${
                              activeJobId === j.id ? "bg-slate-800" : "hover:bg-slate-800/60"
                            }`}
                          >
                            <div className="flex items-center justify-between gap-2 pr-14">
                              <span className="truncate text-sm font-medium text-white">{j.domain}</span>
                              <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] ${getStatusColor(j.status)}`}>
                                {j.status}
                              </span>
                            </div>
                            <div className="mt-1 flex items-center justify-between text-[11px] text-slate-500">
                              <span>{j.total_urls_checked} / {j.total_urls_found} URLs</span>
                              <span>{new Date(j.created_at).toLocaleDateString()}</span>
                            </div>

                            {/* Row actions - only visible on hover so the list stays scannable */}
                            <div className="absolute right-2 top-2 flex items-center gap-1 opacity-0 transition group-hover:opacity-100">
                              {(j.status === "running" || j.status === "pending") && (
                                <button
                                  onClick={(e) => { e.stopPropagation(); cancelCrawl(j.id); }}
                                  disabled={isCancelling}
                                  title="Stop this crawl"
                                  className="rounded p-1 text-slate-500 transition hover:text-red-400 disabled:opacity-40"
                                >
                                  <Square className="h-3 w-3 fill-current" />
                                </button>
                              )}
                              <button
                                onClick={(e) => { e.stopPropagation(); deleteJob(j.id); }}
                                disabled={deletingJobId === j.id}
                                title={confirmDeleteId === j.id ? "Click again to confirm delete" : "Delete this job"}
                                className={`rounded p-1 transition disabled:opacity-40 ${
                                  confirmDeleteId === j.id ? "text-red-400" : "text-slate-500 hover:text-red-400"
                                }`}
                              >
                                {deletingJobId === j.id ? (
                                  <RotateCw className="h-3 w-3 animate-spin" />
                                ) : (
                                  <Trash2 className="h-3 w-3" />
                                )}
                              </button>
                            </div>
                          </div>
                        ))}
                        {jobs.length === 0 && (
                          <div className="py-8 text-center text-xs text-slate-500">No past crawls yet.</div>
                        )}
                      </div>
                    </div>
                  </>,
                  document.body
                )}
              </div>
              <div className="flex items-center gap-2">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-tr from-indigo-500 to-blue-500 text-[10px] font-bold text-white">
                  {user.username?.[0]?.toUpperCase()}
                </div>
                <span className="hidden max-w-[8rem] truncate text-xs font-medium text-slate-300 sm:inline">{user.username}</span>
              </div>
              <button
                onClick={handleLogout}
                className="flex items-center space-x-1 rounded-lg border border-slate-800 px-2 py-1.5 text-xs text-slate-400 transition hover:border-red-500/30 hover:text-red-400 sm:py-1"
                title="Log out"
              >
                <LogOut className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Log out</span>
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Dashboard Panels */}
        <main className="flex-1 space-y-6 overflow-y-auto p-4 sm:space-y-8 sm:p-6 lg:p-8">
          {/* Active Crawls switcher - lets you run several audits at once
              (the backend already supports concurrent jobs) and jump between
              watching whichever one you care about, without digging through
              the full Past Crawls history. */}
          {hasLiveJobs && (
            <div className="flex items-center gap-2 overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/50 p-2">
              <span className="shrink-0 pl-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Active
              </span>
              {jobs.filter(j => j.status === "running" || j.status === "pending").map((j) => (
                <button
                  key={j.id}
                  onClick={() => setActiveJobId(j.id)}
                  className={`flex shrink-0 items-center gap-2 rounded-lg border px-3 py-1.5 text-xs transition ${
                    activeJobId === j.id
                      ? "border-indigo-500/40 bg-indigo-500/10 text-indigo-300"
                      : "border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                  }`}
                >
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-blue-400" />
                  </span>
                  <span className="font-medium">{j.domain}</span>
                  <span className="text-slate-500">{j.total_urls_checked}/{j.total_urls_found || "?"}</span>
                </button>
              ))}
            </div>
          )}

          {/* Retry-all banner for stuck jobs */}
          {hasPendingJobs && (
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 flex items-center justify-between">
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

          {jobDetails ? (
            <>
              {/* Compact "start another audit" bar - the only add-domain form
                  once a job is loaded; the empty state below has its own. */}
              <form
                onSubmit={handleStartCrawl}
                className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-3 sm:flex-row sm:items-center"
              >
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400 sm:shrink-0">
                  <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
                  New audit
                </div>
                <div className="relative w-full sm:w-80">
                  <Globe className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                  <input
                    type="text"
                    placeholder="https://example.com"
                    value={urlInput}
                    onChange={(e) => setUrlInput(e.target.value)}
                    disabled={isSubmitting}
                    className="w-full rounded-lg border border-slate-800 bg-slate-950 py-2 pl-10 pr-3 text-sm text-white placeholder-slate-500 transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-md shadow-indigo-600/25 transition hover:shadow-indigo-500/40 disabled:opacity-50"
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

              {/* Job summary section */}
              <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-slate-900 pb-6 gap-4">
                <div className="flex min-w-0 items-center gap-3 sm:gap-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-slate-800 bg-gradient-to-tr from-slate-900 to-slate-800 text-indigo-400 shadow-lg shadow-black/20 sm:h-12 sm:w-12">
                    <Globe className="h-4.5 w-4.5 sm:h-5 sm:w-5" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                      <h2 className="truncate text-xl font-bold text-white tracking-tight sm:text-2xl">{jobDetails.domain}</h2>
                      <span className={`shrink-0 text-xs px-2.5 py-0.5 rounded-full border ${getStatusColor(jobDetails.status)}`}>
                        {jobDetails.status === "stopping" ? "stopping…" : jobDetails.status}
                      </span>
                    </div>
                    <p className="truncate text-sm text-slate-400 mt-1">Audit URL: <a href={jobDetails.url} target="_blank" rel="noreferrer" className="text-indigo-400 hover:underline">{jobDetails.url}</a></p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="bg-slate-900/60 border border-slate-800 p-3 rounded-xl flex items-center gap-3">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-400">
                      <Clock className="h-4 w-4" />
                    </div>
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
                  <div className="bg-slate-900/60 border border-slate-800 p-3 rounded-xl flex items-center gap-3">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-400">
                      <Gauge className="h-4 w-4" />
                    </div>
                    <div>
                      <div className="text-xs text-slate-400">Speed</div>
                      <div className="text-sm font-semibold text-white">
                        {jobDetails.stats?.speed_urls_per_sec || 0} req/s
                      </div>
                    </div>
                  </div>
                  {(jobDetails.status === "running" || jobDetails.status === "pending") && (
                    <button
                      onClick={() => cancelCrawl(jobDetails.id)}
                      disabled={isCancelling}
                      title="Stop this crawl"
                      className="flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/5 px-3 py-3 text-sm font-semibold text-red-400 transition hover:bg-red-500/10 disabled:opacity-50"
                    >
                      {isCancelling ? (
                        <RotateCw className="h-4 w-4 animate-spin" />
                      ) : (
                        <Square className="h-4 w-4 fill-current" />
                      )}
                      <span>Stop</span>
                    </button>
                  )}
                  {jobDetails.status === "stopping" && (
                    <div className="flex items-center gap-2 rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-3 text-sm font-semibold text-amber-400">
                      <RotateCw className="h-4 w-4 animate-spin" />
                      <span>Stopping…</span>
                    </div>
                  )}
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
              <div className="relative overflow-hidden bg-slate-900/30 border border-slate-900/80 p-6 rounded-2xl backdrop-blur-sm space-y-4">
                <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-indigo-500/50 to-transparent" />
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
                <div className="relative overflow-hidden bg-slate-900/50 border border-slate-900 p-6 rounded-2xl flex flex-col justify-between">
                  <div className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-indigo-500 to-blue-500" />
                  <div>
                    <div className="flex items-center gap-2">
                      <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-400">
                        <Activity className="h-3.5 w-3.5" />
                      </div>
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Crawl Progress</h3>
                    </div>
                    <div className="text-3xl font-extrabold text-white mt-3">
                      {jobDetails.progress.total_urls_checked} <span className="text-lg text-slate-500 font-normal">/ {Math.max(jobDetails.progress.total_urls_found, jobDetails.progress.total_urls_checked)} URLs</span>
                    </div>
                  </div>
                  <div className="mt-4">
                    <div className="w-full bg-slate-800/80 h-2 rounded-full overflow-hidden">
                      <div
                        className="bg-gradient-to-r from-indigo-500 to-blue-500 h-full rounded-full transition-all duration-300"
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
                <div className="relative overflow-hidden bg-slate-900/50 border border-slate-900 p-6 rounded-2xl md:col-span-2">
                  <div className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-emerald-500 via-amber-500 to-red-500" />
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-400">
                      <BarChart3 className="h-3.5 w-3.5" />
                    </div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Response Status Distribution</h3>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-4">
                    <div className="bg-slate-950 p-3 rounded-xl border border-slate-900 transition hover:border-emerald-500/30">
                      <div className="flex items-center gap-1.5 text-emerald-400 text-xl font-bold">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                        {jobDetails.progress.urls_2xx}
                      </div>
                      <div className="text-xs text-slate-400 mt-1">2xx Success</div>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-xl border border-slate-900 transition hover:border-blue-500/30">
                      <div className="flex items-center gap-1.5 text-blue-400 text-xl font-bold">
                        <span className="h-1.5 w-1.5 rounded-full bg-blue-400" />
                        {jobDetails.progress.urls_3xx}
                      </div>
                      <div className="text-xs text-slate-400 mt-1">3xx Redirects</div>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-xl border border-slate-900 transition hover:border-amber-500/30">
                      <div className="flex items-center gap-1.5 text-amber-400 text-xl font-bold">
                        <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                        {jobDetails.progress.urls_4xx}
                      </div>
                      <div className="text-xs text-slate-400 mt-1">4xx Client Errors</div>
                    </div>
                    <div className="bg-slate-950 p-3 rounded-xl border border-slate-900 transition hover:border-red-500/30">
                      <div className="flex items-center gap-1.5 text-red-400 text-xl font-bold">
                        <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
                        {jobDetails.progress.urls_5xx + jobDetails.progress.urls_timeout + jobDetails.progress.urls_dns_error}
                      </div>
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
                <div className="bg-slate-900/50 border border-slate-900 rounded-2xl flex flex-col h-96 overflow-hidden shadow-xl shadow-black/10">
                  <div className="border-b border-slate-900 px-4 py-3 bg-slate-900/40 flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <Terminal className="h-4 w-4 text-indigo-400" />
                      <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Activity Log Console</span>
                    </div>
                    <span className="flex h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse"></span>
                  </div>
                  <div className="flex-1 p-4 font-mono text-[11px] text-slate-300 overflow-y-auto space-y-1.5">
                    {jobDetails.logs.map((l, idx) => (
                      <div
                        key={idx}
                        className={`flex gap-2.5 items-start leading-relaxed border-l-2 pl-2.5 py-1 ${
                          l.level === "error" ? "border-red-500/40" : l.level === "warning" ? "border-amber-500/40" : "border-blue-500/30"
                        }`}
                      >
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
                <div className="lg:col-span-2 bg-slate-900/50 border border-slate-900 rounded-2xl flex flex-col h-96 overflow-hidden shadow-xl shadow-black/10">
                  {/* Filter Toolbar */}
                  <div className="border-b border-slate-900 px-4 py-4 sm:px-6 bg-slate-900/40 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                    <div className="flex items-center space-x-2">
                      <List className="h-4 w-4 shrink-0 text-indigo-400" />
                      <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Audited Sitemap URLs</span>
                      <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-semibold text-slate-400">{filteredUrls.length}</span>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <div className="relative flex-1 min-w-[140px]">
                        <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-500" />
                        <input
                          type="text"
                          placeholder="Search URL..."
                          value={searchTerm}
                          onChange={(e) => setSearchTerm(e.target.value)}
                          className="w-full pl-8 pr-3 py-1.5 rounded-lg border border-slate-800 bg-slate-950 text-xs text-white placeholder-slate-500 transition focus:outline-none focus:border-indigo-500"
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
                        className="flex shrink-0 items-center space-x-1.5 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 hover:shadow-lg hover:shadow-indigo-600/25 px-3 py-1.5 text-xs font-semibold text-white transition focus:outline-none"
                        title="Download CSV report"
                      >
                        <Download className="h-3.5 w-3.5" />
                        <span>Download CSV</span>
                      </button>
                      <button
                        onClick={downloadPdf}
                        disabled={isDownloadingPdf}
                        className="flex shrink-0 items-center space-x-1.5 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 px-3 py-1.5 text-xs font-semibold text-white transition focus:outline-none disabled:opacity-50"
                        title="Download PDF report"
                      >
                        {isDownloadingPdf ? (
                          <RotateCw className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <FileText className="h-3.5 w-3.5" />
                        )}
                        <span>PDF</span>
                      </button>
                    </div>
                  </div>

                  {/* URLs List Container */}
                  <div className="flex-1 overflow-auto">
                    <table className="w-full text-left border-collapse">
                      <thead className="sticky top-0 z-10">
                        <tr className="border-b border-slate-900 bg-slate-900/95 backdrop-blur text-xs font-medium text-slate-400">
                          <th className="px-6 py-3">Audited URL</th>
                          <th className="px-6 py-3">Status</th>
                          <th className="px-6 py-3">Time</th>
                          <th className="px-6 py-3">Type</th>
                          <th className="px-6 py-3"></th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-900/70 text-xs text-slate-300">
                        {filteredUrls.map((u) => {
                          return (
                            <tr key={u.id} className="hover:bg-indigo-500/5 transition">
                              <td className="px-6 py-3.5 font-medium text-white max-w-sm truncate" title={u.url}>
                                {u.url}
                              </td>
                              <td className="px-6 py-3.5">
                                {u.crawl_status === "pending" ? (
                                  <span className="px-2 py-0.5 rounded-full font-mono bg-slate-800 text-slate-400 border border-slate-700/50">
                                    Pending
                                  </span>
                                ) : u.crawl_status === "checking" ? (
                                  <span className="px-2 py-0.5 rounded-full font-mono bg-blue-500/10 text-blue-400 border border-blue-500/20 animate-pulse">
                                    Checking...
                                  </span>
                                ) : (
                                  <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full font-mono border ${
                                    u.status_code && u.status_code < 300 ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" :
                                    u.status_code && u.status_code < 400 ? "bg-blue-500/10 text-blue-400 border-blue-500/20" :
                                    "bg-red-500/10 text-red-400 border-red-500/20"
                                  }`}>
                                    <span className={`h-1.5 w-1.5 rounded-full ${
                                      u.status_code && u.status_code < 300 ? "bg-emerald-400" :
                                      u.status_code && u.status_code < 400 ? "bg-blue-400" : "bg-red-400"
                                    }`} />
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
            <div className="flex h-full min-h-[70vh] flex-col items-center justify-center gap-10 py-12 text-slate-500 lg:flex-row lg:gap-16">
              <div className="w-full max-w-md text-center lg:text-left">
                <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-indigo-500/20 bg-indigo-500/10 px-3 py-1 text-xs font-medium text-indigo-300">
                  <Sparkles className="h-3.5 w-3.5" />
                  Start your first audit
                </div>
                <h3 className="text-2xl font-bold text-white tracking-tight">Audit a new domain</h3>
                <p className="mt-1.5 text-sm">Enter a domain and we'll discover its sitemaps, crawl every URL, and flag issues live.</p>
                <form onSubmit={handleStartCrawl} className="mt-6 flex flex-col gap-3 sm:flex-row">
                  <div className="relative flex-1">
                    <Globe className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                    <input
                      type="text"
                      placeholder="https://example.com"
                      value={urlInput}
                      onChange={(e) => setUrlInput(e.target.value)}
                      disabled={isSubmitting}
                      className="w-full rounded-xl border border-slate-800 bg-slate-900 py-3 pl-10 pr-3 text-sm text-white placeholder-slate-500 transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-600/25 transition hover:shadow-indigo-500/40 disabled:opacity-50"
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
              <AuditPreviewCard />
            </div>
          )}
        </main>
      </div>

      {selectedUrl && <PageDetailModal page={selectedUrl} onClose={() => setSelectedUrl(null)} />}
    </div>
  );
}
