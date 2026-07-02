"use client";

import React from "react";
import { Globe } from "lucide-react";

interface CrawlingAnimationProps {
  domain: string;
  urlsChecked: number;
  urlsFound: number;
  percent: number;
}

/** Radar-sweep style "actively crawling" indicator - a spider/bot sweeping
 * outward from the domain, pinging discovered URL nodes around it. */
export default function CrawlingAnimation({ domain, urlsChecked, urlsFound, percent }: CrawlingAnimationProps) {
  const nodeAngles = [20, 65, 110, 155, 200, 245, 290, 335];

  return (
    <div className="relative overflow-hidden rounded-2xl border border-slate-900 bg-gradient-to-br from-indigo-950/30 via-slate-900/50 to-slate-950 p-8">
      <div className="flex flex-col items-center gap-6 sm:flex-row sm:justify-between">
        {/* Radar visual */}
        <div className="relative h-36 w-36 shrink-0">
          {/* Concentric rings */}
          <div className="absolute inset-0 rounded-full border border-indigo-500/20" />
          <div className="absolute inset-4 rounded-full border border-indigo-500/20" />
          <div className="absolute inset-8 rounded-full border border-indigo-500/20" />

          {/* Rotating sweep */}
          <div
            className="absolute inset-0 rounded-full opacity-70"
            style={{
              background: "conic-gradient(from 0deg, transparent 0deg, transparent 300deg, rgba(99,102,241,0.55) 340deg, transparent 360deg)",
              animation: "crawl-spin 2.2s linear infinite",
            }}
          />

          {/* URL nodes pinging around the ring */}
          {nodeAngles.map((angle, i) => {
            const rad = (angle * Math.PI) / 180;
            const radius = 58;
            const x = 72 + radius * Math.cos(rad);
            const y = 72 + radius * Math.sin(rad);
            return (
              <span
                key={angle}
                className="absolute h-1.5 w-1.5 rounded-full bg-indigo-400"
                style={{
                  left: x,
                  top: y,
                  animation: `crawl-ping 2.2s ease-in-out ${i * 0.27}s infinite`,
                }}
              />
            );
          })}

          {/* Center: our logo, pulsing like an active bot */}
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-gradient-to-tr from-blue-600 to-indigo-600 shadow-lg shadow-indigo-500/40">
              <Globe className="h-5 w-5 animate-pulse text-white" />
            </div>
          </div>
        </div>

        {/* Text + progress */}
        <div className="w-full flex-1 text-center sm:text-left">
          <h2 className="text-2xl font-bold text-white">
            We're crawling: <span className="text-indigo-400">{domain}</span>
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Discovering sitemaps and auditing every page as it's found.
          </p>

          <div className="mt-5">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>{urlsChecked} of {urlsFound || "?"} URLs checked</span>
              <span className="font-mono text-slate-300">{percent}%</span>
            </div>
            <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-slate-850 bg-slate-800">
              <div
                className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-blue-500 transition-all duration-500"
                style={{ width: `${Math.min(percent, 100)}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      <style jsx>{`
        @keyframes crawl-spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes crawl-ping {
          0%, 100% { opacity: 0.25; transform: scale(1); }
          50% { opacity: 1; transform: scale(1.8); box-shadow: 0 0 8px 2px rgba(99,102,241,0.6); }
        }
      `}</style>
    </div>
  );
}
