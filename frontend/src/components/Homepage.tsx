"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Globe, ArrowRight, CheckCircle2, Zap } from "lucide-react";
import AuditPreviewCard from "@/components/AuditPreviewCard";

const PENDING_URL_KEY = "crawler_pending_url";

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
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-5 md:px-12">
        <div className="flex items-center space-x-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 shadow-lg shadow-indigo-500/20">
            <Globe className="h-4.5 w-4.5 text-white" />
          </div>
          <span className="text-base font-bold tracking-tight text-white">Popz AI Crawl</span>
        </div>
        <button
          onClick={() => router.push("/login")}
          className="rounded-lg border border-slate-800 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-700 hover:text-white"
        >
          Sign in
        </button>
      </header>

      {/* Split hero */}
      <div className="grid grid-cols-1 lg:grid-cols-2">
        {/* Left: pitch + form */}
        <div className="flex flex-col justify-center px-6 py-16 md:px-12 lg:py-24">
          <div className="max-w-md">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-indigo-500/20 bg-indigo-500/10 px-3 py-1 text-xs font-medium text-indigo-300">
              <Zap className="h-3.5 w-3.5" />
              Sitemap-based crawling, no JS rendering needed
            </div>

            <h1 className="text-4xl font-extrabold leading-tight tracking-tight text-white md:text-5xl">
              Audit every page on your site, straight from its sitemap.
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
                <input
                  type="text"
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  placeholder="e.g. https://example.com"
                  className="flex-1 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
                />
                <button
                  type="submit"
                  className="flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500"
                >
                  Start Free Audit
                  <ArrowRight className="h-4 w-4" />
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
        <div className="relative flex items-center justify-center overflow-hidden bg-gradient-to-br from-indigo-950/40 via-slate-950 to-slate-950 px-6 py-16 md:px-12 lg:py-24">
          <div className="absolute h-72 w-72 rounded-full bg-indigo-500/10 blur-3xl" />
          <AuditPreviewCard />
        </div>
      </div>
    </div>
  );
}

export { PENDING_URL_KEY };
