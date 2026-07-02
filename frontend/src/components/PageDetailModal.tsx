"use client";

import React from "react";
import { X, Image as ImageIcon, Link2, Tags, BarChart3, AlertTriangle } from "lucide-react";

interface ImageMeta {
  src: string;
  alt: string;
  width?: string;
  height?: string;
}

interface PageMetadata {
  title?: string;
  meta_description?: string;
  h1?: string;
  h2?: string[];
  h3?: string[];
  word_count?: number;
  canonical_url?: string;
  lang?: string;
  robots?: string;
  og_tags?: Record<string, string>;
  twitter_tags?: Record<string, string>;
  json_ld?: any[];
  schema_org?: any[];
  images?: ImageMeta[];
  internal_links?: number;
  external_links?: number;
  analytics?: {
    google_analytics?: boolean;
    gtag?: boolean;
    facebook_pixel?: boolean;
    hotjar?: boolean;
    mixpanel?: boolean;
  };
}

interface PageDetailUrl {
  id: string;
  url: string;
  status_code: number | null;
  status_category: string | null;
  response_time_ms: number | null;
  content_type: string | null;
  canonical_url: string | null;
  is_indexable: boolean | null;
  crawl_status?: string;
  metadata: PageMetadata | null;
  seo_issues?: { type: string; category: string; issue: string; details: string }[];
}

export default function PageDetailModal({ page, onClose }: { page: PageDetailUrl; onClose: () => void }) {
  const meta = page.metadata || {};
  const missingAlt = (meta.images || []).filter((i) => !i.alt).length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-slate-800 bg-slate-950 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 flex items-start justify-between border-b border-slate-900 bg-slate-950/95 px-6 py-4 backdrop-blur">
          <div className="min-w-0 pr-4">
            <h2 className="truncate text-sm font-semibold text-white" title={page.url}>{page.url}</h2>
            <p className="mt-1 truncate text-xs text-slate-400">{meta.title || "No title tag found"}</p>
          </div>
          <button onClick={onClose} className="shrink-0 rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-900 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-6 p-6">
          {/* Overview */}
          <section>
            <h3 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
              <BarChart3 className="h-3.5 w-3.5" /> Overview
            </h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Stat label="Status Code" value={page.status_code ?? "—"} tone={page.status_code && page.status_code < 300 ? "good" : page.status_code ? "bad" : "neutral"} />
              <Stat label="Response Time" value={page.response_time_ms ? `${page.response_time_ms}ms` : "—"} />
              <Stat label="Content Type" value={page.content_type || "—"} />
              <Stat label="Indexable" value={page.is_indexable === null ? "—" : page.is_indexable ? "Yes" : "No"} tone={page.is_indexable === false ? "bad" : "good"} />
              <Stat label="Word Count" value={meta.word_count ?? "—"} />
              <Stat label="Language" value={meta.lang || "—"} />
            </div>
          </section>

          {/* Content */}
          <section>
            <h3 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
              <Tags className="h-3.5 w-3.5" /> Content
            </h3>
            <div className="space-y-3 text-xs">
              <Field label="Title" value={meta.title} empty="Missing title tag" />
              <Field label="Meta Description" value={meta.meta_description} empty="Missing meta description" />
              <Field label="H1" value={meta.h1} empty="Missing H1" />
              <Field label="Canonical URL" value={meta.canonical_url || page.canonical_url || undefined} empty="No canonical URL" />
              <Field label="Robots Meta" value={meta.robots} empty="No robots meta tag" />
              {!!(meta.h2 && meta.h2.length) && (
                <div>
                  <span className="text-slate-500">H2 tags ({meta.h2.length}):</span>
                  <ul className="mt-1 list-inside list-disc space-y-0.5 text-slate-300">
                    {meta.h2.slice(0, 6).map((h, i) => <li key={i} className="truncate">{h}</li>)}
                  </ul>
                </div>
              )}
            </div>
          </section>

          {/* Links & Images */}
          <section>
            <h3 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
              <Link2 className="h-3.5 w-3.5" /> Links & Images
            </h3>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Internal Links" value={meta.internal_links ?? "—"} />
              <Stat label="External Links" value={meta.external_links ?? "—"} />
              <Stat label="Images" value={meta.images?.length ?? 0} />
              <Stat label="Missing Alt" value={missingAlt} tone={missingAlt > 0 ? "bad" : "good"} />
            </div>
            {!!(meta.images && meta.images.length) && (
              <div className="mt-3 max-h-40 overflow-y-auto rounded-lg border border-slate-900">
                {meta.images.slice(0, 20).map((img, i) => (
                  <div key={i} className="flex items-center gap-2 border-b border-slate-900 px-3 py-2 text-[11px] last:border-0">
                    <ImageIcon className="h-3 w-3 shrink-0 text-slate-500" />
                    <span className="flex-1 truncate text-slate-400" title={img.src}>{img.src}</span>
                    {img.alt ? (
                      <span className="shrink-0 text-emerald-400">has alt</span>
                    ) : (
                      <span className="shrink-0 text-amber-400">no alt</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Tracking */}
          {meta.analytics && (
            <section>
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Tracking Detected</h3>
              <div className="flex flex-wrap gap-2">
                {meta.analytics.google_analytics && <Badge label="Google Analytics" />}
                {meta.analytics.gtag && <Badge label="gtag.js" />}
                {meta.analytics.facebook_pixel && <Badge label="Facebook Pixel" />}
                {meta.analytics.hotjar && <Badge label="Hotjar" />}
                {meta.analytics.mixpanel && <Badge label="Mixpanel" />}
                {!Object.values(meta.analytics).some(Boolean) && <span className="text-xs text-slate-500">None detected</span>}
              </div>
            </section>
          )}

          {/* Issues */}
          {!!(page.seo_issues && page.seo_issues.length) && (
            <section>
              <h3 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
                <AlertTriangle className="h-3.5 w-3.5" /> Issues ({page.seo_issues.length})
              </h3>
              <div className="space-y-2">
                {page.seo_issues.map((issue, i) => (
                  <div key={i} className={`rounded-lg border px-3 py-2 text-xs ${
                    issue.type === "error" ? "border-red-500/20 bg-red-500/5 text-red-300" : "border-amber-500/20 bg-amber-500/5 text-amber-300"
                  }`}>
                    <span className="font-semibold">{issue.issue}</span>
                    <span className="text-slate-400"> — {issue.details}</span>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: React.ReactNode; tone?: "good" | "bad" | "neutral" }) {
  const color = tone === "good" ? "text-emerald-400" : tone === "bad" ? "text-red-400" : "text-white";
  return (
    <div className="rounded-lg border border-slate-900 bg-slate-900/50 p-2.5">
      <div className={`text-sm font-semibold ${color}`}>{value}</div>
      <div className="mt-0.5 text-[10px] text-slate-500">{label}</div>
    </div>
  );
}

function Field({ label, value, empty }: { label: string; value?: string; empty: string }) {
  return (
    <div>
      <span className="text-slate-500">{label}:</span>{" "}
      {value ? <span className="text-slate-200">{value}</span> : <span className="italic text-amber-400/80">{empty}</span>}
    </div>
  );
}

function Badge({ label }: { label: string }) {
  return (
    <span className="rounded-full border border-indigo-500/20 bg-indigo-500/10 px-2.5 py-1 text-[11px] font-medium text-indigo-300">
      {label}
    </span>
  );
}
