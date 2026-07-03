"use client";

import React from "react";
import { Activity, CheckCircle2, Clock, ShieldCheck, Terminal } from "lucide-react";

/** Stylized preview of a live crawl - used on the marketing homepage and as
 * the dashboard's empty state before a job is selected. Purely illustrative
 * (mocked numbers), not wired to real data. */
export default function AuditPreviewCard() {
  return (
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
      <div className="absolute -right-2 -top-2 rounded-xl border border-slate-800 bg-slate-900 p-2.5 shadow-xl shadow-black/40 sm:-right-4 sm:-top-4 sm:p-3">
        <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
          <Clock className="h-3 w-3" /> Speed
        </div>
        <div className="mt-1 text-base font-bold text-white sm:text-lg">4.2 <span className="text-xs font-normal text-slate-500">req/s</span></div>
      </div>

      {/* Floating URL count badge */}
      <div className="absolute -bottom-3 -left-2 rounded-xl border border-slate-800 bg-slate-900 p-2.5 shadow-xl shadow-black/40 sm:-bottom-5 sm:-left-5 sm:p-3">
        <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
          <ShieldCheck className="h-3 w-3" /> URLs Discovered
        </div>
        <div className="mt-1 text-base font-bold text-white sm:text-lg">3,482</div>
      </div>
    </div>
  );
}
