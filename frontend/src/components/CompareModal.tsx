"use client";

import React, { useState, useEffect } from "react";
import axios from "axios";
import { X, GitCompare, TrendingDown, TrendingUp, PlusCircle, MinusCircle, RefreshCw, RotateCw } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ComparableJob {
  id: string;
  created_at: string;
  total_urls_checked: number;
}

interface StatusChange {
  url: string;
  old_status: number | null;
  new_status: number | null;
}

interface CompareResult {
  older_job: { id: string; created_at: string; total_urls_checked: number };
  newer_job: { id: string; created_at: string; total_urls_checked: number };
  summary: {
    urls_added: number;
    urls_removed: number;
    newly_broken: number;
    newly_fixed: number;
    status_changed: number;
  };
  added_urls: string[];
  removed_urls: string[];
  newly_broken: StatusChange[];
  newly_fixed: StatusChange[];
  status_changes: StatusChange[];
}

export default function CompareModal({ jobId, domain, onClose }: { jobId: string; domain: string; onClose: () => void }) {
  const [comparableJobs, setComparableJobs] = useState<ComparableJob[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [comparing, setComparing] = useState(false);
  const [result, setResult] = useState<CompareResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    axios.get(`${API_BASE}/api/crawl/jobs/${jobId}/comparable`)
      .then((res) => setComparableJobs(res.data))
      .catch(() => setError("Failed to load past crawls for this domain."))
      .finally(() => setLoadingList(false));
  }, [jobId]);

  const runCompare = async () => {
    if (!selectedJobId) return;
    setComparing(true);
    setError(null);
    try {
      const res = await axios.get(`${API_BASE}/api/crawl/jobs/${jobId}/compare/${selectedJobId}`);
      setResult(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.message || "Failed to compare these crawls.");
    } finally {
      setComparing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-slate-800 bg-slate-950 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 flex items-start justify-between border-b border-slate-900 bg-slate-950/95 px-6 py-4 backdrop-blur">
          <div className="min-w-0 pr-4">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
              <GitCompare className="h-4 w-4 text-indigo-400" /> Compare Crawls
            </h2>
            <p className="mt-1 truncate text-xs text-slate-400">{domain}</p>
          </div>
          <button onClick={onClose} className="shrink-0 rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-900 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-6 p-6">
          {!result && (
            <div className="space-y-3">
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                Compare this crawl against
              </label>
              {loadingList ? (
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <RotateCw className="h-3.5 w-3.5 animate-spin" /> Loading past crawls…
                </div>
              ) : comparableJobs.length === 0 ? (
                <p className="text-xs text-slate-500">
                  No other crawls of this domain have comparison data yet. Run another audit on {domain} to compare against this one.
                </p>
              ) : (
                <div className="flex flex-col gap-3 sm:flex-row">
                  <select
                    value={selectedJobId}
                    onChange={(e) => setSelectedJobId(e.target.value)}
                    className="flex-1 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none"
                  >
                    <option value="">Select a past crawl…</option>
                    {comparableJobs.map((j) => (
                      <option key={j.id} value={j.id}>
                        {new Date(j.created_at).toLocaleString()} ({j.total_urls_checked} URLs)
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={runCompare}
                    disabled={!selectedJobId || comparing}
                    className="flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-md shadow-indigo-600/25 transition hover:shadow-indigo-500/40 disabled:opacity-50"
                  >
                    {comparing ? <RotateCw className="h-4 w-4 animate-spin" /> : <GitCompare className="h-4 w-4" />}
                    Compare
                  </button>
                </div>
              )}
              {error && <p className="text-xs text-red-400">{error}</p>}
            </div>
          )}

          {result && (
            <>
              <div className="flex items-center justify-between rounded-lg border border-slate-900 bg-slate-900/50 px-4 py-3 text-xs text-slate-400">
                <span>{new Date(result.older_job.created_at).toLocaleString()} <span className="text-slate-600">({result.older_job.total_urls_checked} URLs)</span></span>
                <span className="text-indigo-400">&rarr;</span>
                <span>{new Date(result.newer_job.created_at).toLocaleString()} <span className="text-slate-600">({result.newer_job.total_urls_checked} URLs)</span></span>
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
                <SummaryStat icon={PlusCircle} label="Added" value={result.summary.urls_added} tone="good" />
                <SummaryStat icon={MinusCircle} label="Removed" value={result.summary.urls_removed} tone="neutral" />
                <SummaryStat icon={TrendingDown} label="Newly Broken" value={result.summary.newly_broken} tone="bad" />
                <SummaryStat icon={TrendingUp} label="Newly Fixed" value={result.summary.newly_fixed} tone="good" />
                <SummaryStat icon={RefreshCw} label="Status Changed" value={result.summary.status_changed} tone="neutral" />
              </div>

              {result.newly_broken.length > 0 && (
                <DiffSection title="Newly Broken URLs" tone="bad">
                  {result.newly_broken.map((c, i) => (
                    <StatusChangeRow key={i} change={c} />
                  ))}
                </DiffSection>
              )}

              {result.newly_fixed.length > 0 && (
                <DiffSection title="Newly Fixed URLs" tone="good">
                  {result.newly_fixed.map((c, i) => (
                    <StatusChangeRow key={i} change={c} />
                  ))}
                </DiffSection>
              )}

              {result.added_urls.length > 0 && (
                <DiffSection title={`New URLs (${result.added_urls.length})`} tone="neutral">
                  {result.added_urls.map((u, i) => (
                    <div key={i} className="truncate px-3 py-1.5 text-xs text-slate-300">{u}</div>
                  ))}
                </DiffSection>
              )}

              {result.removed_urls.length > 0 && (
                <DiffSection title={`Removed URLs (${result.removed_urls.length})`} tone="neutral">
                  {result.removed_urls.map((u, i) => (
                    <div key={i} className="truncate px-3 py-1.5 text-xs text-slate-500 line-through">{u}</div>
                  ))}
                </DiffSection>
              )}

              {result.summary.urls_added === 0 && result.summary.urls_removed === 0 &&
               result.summary.newly_broken === 0 && result.summary.newly_fixed === 0 &&
               result.summary.status_changed === 0 && (
                <p className="text-center text-sm text-slate-500 py-4">No changes between these two crawls.</p>
              )}

              <button
                onClick={() => { setResult(null); setSelectedJobId(""); }}
                className="text-xs font-semibold text-indigo-400 hover:text-indigo-300"
              >
                &larr; Compare a different crawl
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SummaryStat({ icon: Icon, label, value, tone }: { icon: any; label: string; value: number; tone: "good" | "bad" | "neutral" }) {
  const color = tone === "good" ? "text-emerald-400" : tone === "bad" ? "text-red-400" : "text-slate-300";
  return (
    <div className="rounded-lg border border-slate-900 bg-slate-900/50 p-3 text-center">
      <Icon className={`mx-auto h-4 w-4 ${color}`} />
      <div className={`mt-1.5 text-lg font-bold ${color}`}>{value}</div>
      <div className="mt-0.5 text-[10px] text-slate-500">{label}</div>
    </div>
  );
}

function DiffSection({ title, tone, children }: { title: string; tone: "good" | "bad" | "neutral"; children: React.ReactNode }) {
  const border = tone === "good" ? "border-emerald-500/20" : tone === "bad" ? "border-red-500/20" : "border-slate-800";
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">{title}</h3>
      <div className={`max-h-48 overflow-y-auto rounded-lg border ${border} divide-y divide-slate-900`}>
        {children}
      </div>
    </section>
  );
}

function StatusChangeRow({ change }: { change: StatusChange }) {
  return (
    <div className="flex items-center justify-between gap-3 px-3 py-1.5 text-xs">
      <span className="truncate text-slate-300">{change.url}</span>
      <span className="shrink-0 font-mono text-slate-500">
        {change.old_status ?? "-"} <span className="text-slate-600">&rarr;</span> {change.new_status ?? "-"}
      </span>
    </div>
  );
}
