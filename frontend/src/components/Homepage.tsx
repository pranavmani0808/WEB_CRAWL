"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Globe, ArrowRight, CheckCircle2, Activity, Clock,
  ShieldCheck, Terminal, Zap,
} from "lucide-react";

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

          <div className="relative w-full max-w-md">
            {/* Main preview card */}
            <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-2xl shadow-black/40 backdrop-blur">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-indigo-400" />
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">Live Audit Pipeline</span>
                </div>
                <span className="flex items-center gap-1.5 rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] font-medium text-blue-400">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-400" />
                  Crawling Live
                </span>
              </div>

              <div className="mt-5 flex items-center justify-between">
                {["Domain", "DNS", "SSL", "Sitemap", "Crawl"].map((label, i) => (
                  <React.Fragment key={label}>
                    <div className="flex flex-col items-center gap-1.5">
                      <div className={`flex h-7 w-7 items-center justify-center rounded-full border-2 ${
                        i < 4 ? "border-indigo-500 bg-indigo-500/20" : "border-slate-700 bg-slate-800"
                      }`}>
                        {i < 4 ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-indigo-400" />
                        ) : (
                          <span className="h-2 w-2 animate-pulse rounded-full bg-slate-500" />
                        )}
                      </div>
                      <span className="text-[9px] text-slate-500">{label}</span>
                    </div>
                    {i < 4 && <div className={`h-px flex-1 ${i < 3 ? "bg-indigo-500/40" : "bg-slate-800"}`} />}
                  </React.Fragment>
                ))}
              </div>

              <div className="mt-6">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">Crawl Progress</span>
                  <span className="font-mono text-slate-300">142 / 170 URLs</span>
                </div>
                <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-slate-850 bg-slate-800">
                  <div className="h-full w-[84%] rounded-full bg-gradient-to-r from-indigo-500 to-blue-500" />
                </div>
              </div>

              <div className="mt-5 grid grid-cols-3 gap-2">
                <div className="rounded-lg border border-slate-800 bg-slate-950 p-2.5 text-center">
                  <div className="text-lg font-bold text-emerald-400">128</div>
                  <div className="text-[9px] text-slate-500">2xx Success</div>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-950 p-2.5 text-center">
                  <div className="text-lg font-bold text-amber-400">9</div>
                  <div className="text-[9px] text-slate-500">4xx Errors</div>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-950 p-2.5 text-center">
                  <div className="text-lg font-bold text-red-400">0</div>
                  <div className="text-[9px] text-slate-500">Failed</div>
                </div>
              </div>

              <div className="mt-5 rounded-lg border border-slate-800 bg-slate-950 p-3 font-mono text-[10px] text-slate-500">
                <div className="flex items-center gap-1.5 text-slate-400">
                  <Terminal className="h-3 w-3" /> Activity Log
                </div>
                <div className="mt-2 space-y-1 leading-relaxed">
                  <div><span className="text-blue-400">[info]</span> robots.txt fetched successfully</div>
                  <div><span className="text-amber-400">[warn]</span> Meta description too long</div>
                  <div><span className="text-blue-400">[info]</span> Discovered 4 sitemaps, 170 URLs</div>
                </div>
              </div>
            </div>

            {/* Floating speed badge */}
            <div className="absolute -right-4 -top-4 rounded-xl border border-slate-800 bg-slate-900 p-3 shadow-xl shadow-black/40">
              <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
                <Clock className="h-3 w-3" /> Speed
              </div>
              <div className="mt-1 text-lg font-bold text-white">4.2 <span className="text-xs font-normal text-slate-500">req/s</span></div>
            </div>

            {/* Floating URL count badge */}
            <div className="absolute -bottom-5 -left-5 rounded-xl border border-slate-800 bg-slate-900 p-3 shadow-xl shadow-black/40">
              <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
                <ShieldCheck className="h-3 w-3" /> URLs Discovered
              </div>
              <div className="mt-1 text-lg font-bold text-white">3,482</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export { PENDING_URL_KEY };
