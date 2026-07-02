"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Globe, ArrowRight, CheckCircle2, Zap, Radar, ListTree, FileDown, Gauge,
} from "lucide-react";
import AuditPreviewCard from "@/components/AuditPreviewCard";

const PENDING_URL_KEY = "crawler_pending_url";

const FEATURES = [
  {
    icon: Radar,
    title: "Sitemap-first discovery",
    desc: "Parses XML sitemaps and sitemap indexes directly, so every page is found up front without slow JS rendering.",
  },
  {
    icon: Gauge,
    title: "Live crawl pipeline",
    desc: "Watch domain checks, DNS, SSL, and URL audits update in real time as the crawl runs, stage by stage.",
  },
  {
    icon: ListTree,
    title: "Per-page detail",
    desc: "Drill into any URL for title, meta tags, headings, images, links, and detected SEO issues.",
  },
  {
    icon: FileDown,
    title: "One-click CSV export",
    desc: "Export the full audited URL list with status codes, response times, and indexability for reporting.",
  },
];

export default function Homepage() {
  const router = useRouter();
  const [urlInput, setUrlInput] = useState("");

  const handleGetStarted = (e: React.FormEvent) => {
    e.preventDefault();
    if (urlInput.trim()) {
      localStorage.setItem(PENDING_URL_KEY, urlInput.trim());
    }
    router.push("/login");
  };

  return (
    <div className="min-h-screen bg-slate-950 font-sans text-slate-100">
      {/* Header */}
      <header className="sticky top-0 z-20 border-b border-slate-900/80 bg-slate-950/70 backdrop-blur-lg">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 md:px-12">
          <div className="flex items-center space-x-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 shadow-lg shadow-indigo-500/20">
              <Globe className="h-4.5 w-4.5 text-white" />
            </div>
            <span className="text-base font-bold tracking-tight text-white">Popz AI Crawl</span>
          </div>
          <button
            onClick={() => router.push("/login")}
            className="rounded-lg border border-slate-800 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-700 hover:bg-slate-900 hover:text-white"
          >
            Sign in
          </button>
        </div>
      </header>

      {/* Split hero */}
      <div className="relative mx-auto grid max-w-7xl grid-cols-1 lg:grid-cols-2">
        <div className="pointer-events-none absolute -top-24 left-0 h-96 w-96 rounded-full bg-indigo-600/10 blur-[110px]" />

        {/* Left: pitch + form */}
        <div className="relative flex flex-col justify-center px-6 py-16 md:px-12 lg:py-28">
          <div className="max-w-md">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-indigo-500/20 bg-indigo-500/10 px-3 py-1 text-xs font-medium text-indigo-300">
              <Zap className="h-3.5 w-3.5" />
              Sitemap-based crawling, no JS rendering needed
            </div>

            <h1 className="text-4xl font-extrabold leading-tight tracking-tight text-white md:text-5xl">
              Audit every page on <span className="text-gradient">your site</span>, straight from its sitemap.
            </h1>
            <p className="mt-5 text-base text-slate-400">
              Popz AI Crawl discovers every URL in your XML sitemaps, checks
              each one's response status and load time, and flags SEO,
              accessibility, and technical issues — live, as it crawls.
            </p>

            <form onSubmit={handleGetStarted} className="mt-8 space-y-3">
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                Add your domain
              </label>
              <div className="flex flex-col gap-3 sm:flex-row">
                <div className="relative flex-1">
                  <Globe className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                  <input
                    type="text"
                    value={urlInput}
                    onChange={(e) => setUrlInput(e.target.value)}
                    placeholder="e.g. https://example.com"
                    className="w-full rounded-xl border border-slate-800 bg-slate-900 py-3 pl-10 pr-4 text-sm text-white placeholder-slate-500 transition focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <button
                  type="submit"
                  className="group flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-600/25 transition hover:shadow-indigo-500/40"
                >
                  Start Free Audit
                  <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
                </button>
              </div>
              <p className="text-xs text-slate-500">
                Free account required — no credit card. Enter a domain and we'll pick up where you left off after you sign in.
              </p>
            </form>

            <div className="mt-10 flex flex-wrap gap-x-6 gap-y-3 text-xs text-slate-500">
              <span className="flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> Live pipeline visibility</span>
              <span className="flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> Per-user job history</span>
              <span className="flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> CSV export</span>
            </div>
          </div>
        </div>

        {/* Right: product preview */}
        <div className="relative flex items-center justify-center overflow-hidden px-6 py-16 md:px-12 lg:py-28">
          <div className="absolute h-72 w-72 rounded-full bg-indigo-500/10 blur-3xl" />
          <AuditPreviewCard />
        </div>
      </div>

      {/* Feature strip */}
      <div className="border-t border-slate-900/80 bg-slate-900/20">
        <div className="mx-auto max-w-7xl px-6 py-16 md:px-12 lg:py-20">
          <div className="max-w-xl">
            <h2 className="text-2xl font-bold tracking-tight text-white md:text-3xl">Built for a full site audit, not a single page.</h2>
            <p className="mt-3 text-sm text-slate-400">Everything you need to know your site's real footprint — before search engines find the problems for you.</p>
          </div>
          <div className="mt-10 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="group rounded-2xl border border-slate-800 bg-slate-900/50 p-5 transition hover:border-indigo-500/30 hover:bg-slate-900"
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-indigo-500/20 bg-indigo-500/10 text-indigo-400 transition group-hover:bg-indigo-500/20">
                  <f.icon className="h-5 w-5" />
                </div>
                <h3 className="mt-4 text-sm font-semibold text-white">{f.title}</h3>
                <p className="mt-1.5 text-xs leading-relaxed text-slate-400">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-slate-900/80">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-6 py-8 text-xs text-slate-500 md:flex-row md:px-12">
          <div className="flex items-center space-x-2">
            <Globe className="h-3.5 w-3.5" />
            <span>Popz AI Crawl</span>
          </div>
          <span>Sitemap-based domain inventory auditing.</span>
        </div>
      </footer>
    </div>
  );
}

export { PENDING_URL_KEY };
