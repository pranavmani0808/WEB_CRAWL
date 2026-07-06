"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import axios from "axios";
import {
  Users, Activity, Globe, BarChart3, ShieldCheck, RotateCw, ChevronLeft,
  ArrowLeft, Eye, LogOut,
} from "lucide-react";
import { restoreSession, clearSession, AuthUser } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Overview {
  users: { total: number; active: number; new_last_7d: number };
  crawls: { total: number; running: number; completed: number; failed: number; last_7d: number };
  domains: number;
  total_urls_checked: number;
}

interface AdminUser {
  id: string;
  email: string;
  username: string;
  is_active: boolean;
  is_admin: boolean;
  created_at: string | null;
  total_crawls: number;
  active_crawls: number;
  urls_checked: number;
  last_crawl_at: string | null;
}

interface UserCrawl {
  id: string;
  domain: string;
  status: string;
  total_urls_checked: number;
  total_urls_found: number;
  created_at: string | null;
  completed_at: string | null;
}

const fmt = (s: string | null) => (s ? new Date(s + (/[Z+]$/.test(s) ? "" : "Z")).toLocaleString() : "—");

export default function AdminDashboard() {
  const router = useRouter();
  const [checked, setChecked] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<AdminUser | null>(null);
  const [crawls, setCrawls] = useState<UserCrawl[]>([]);
  const [loadingCrawls, setLoadingCrawls] = useState(false);

  // Auth gate: must be logged in AND admin.
  useEffect(() => {
    const restored = restoreSession();
    if (!restored) { router.replace("/login"); return; }
    if (!restored.is_admin) { router.replace("/"); return; }
    setUser(restored);
    setChecked(true);
  }, [router]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [ov, us] = await Promise.all([
        axios.get(`${API_BASE}/api/admin/overview`),
        axios.get(`${API_BASE}/api/admin/users`),
      ]);
      setOverview(ov.data);
      setUsers(us.data);
    } catch (err: any) {
      setError(err?.response?.status === 403 ? "You don't have admin access." : "Failed to load admin data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (checked) load(); }, [checked]);

  const openUser = async (u: AdminUser) => {
    setSelected(u);
    setLoadingCrawls(true);
    try {
      const res = await axios.get(`${API_BASE}/api/admin/users/${u.id}/crawls`);
      setCrawls(res.data.crawls);
    } catch { setCrawls([]); } finally { setLoadingCrawls(false); }
  };

  if (!checked) return <div className="min-h-screen bg-slate-950" />;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      {/* Header */}
      <header className="border-b border-slate-900 bg-slate-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500/15 text-indigo-400">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-base font-bold text-white">Admin Dashboard</h1>
              <p className="text-xs text-slate-500">Popz AI Crawl · platform monitoring</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => router.push("/")} className="flex items-center gap-1.5 rounded-lg border border-slate-800 px-3 py-1.5 text-xs text-slate-300 transition hover:border-indigo-500/40 hover:text-white">
              <ArrowLeft className="h-3.5 w-3.5" /> App
            </button>
            <button onClick={load} className="rounded-lg border border-slate-800 p-1.5 text-slate-400 transition hover:text-white" title="Refresh">
              <RotateCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            </button>
            <button onClick={() => { clearSession(); router.replace("/login"); }} className="flex items-center gap-1.5 rounded-lg border border-slate-800 px-3 py-1.5 text-xs text-slate-300 transition hover:border-red-500/40 hover:text-red-300">
              <LogOut className="h-3.5 w-3.5" /> Log out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {error && <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</div>}

        {/* Overview cards */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <StatCard icon={Users} label="Total Users" value={overview?.users.total} sub={`${overview?.users.new_last_7d ?? 0} new / 7d`} />
          <StatCard icon={Activity} label="Active Crawls" value={overview?.crawls.running} tone="indigo" />
          <StatCard icon={BarChart3} label="Total Crawls" value={overview?.crawls.total} sub={`${overview?.crawls.last_7d ?? 0} / 7d`} />
          <StatCard icon={BarChart3} label="Completed" value={overview?.crawls.completed} tone="green" />
          <StatCard icon={BarChart3} label="Failed" value={overview?.crawls.failed} tone="red" />
          <StatCard icon={Globe} label="URLs Audited" value={overview?.total_urls_checked} />
        </div>

        {/* Users table */}
        <div className="mt-6 overflow-hidden rounded-xl border border-slate-900 bg-slate-900/40">
          <div className="flex items-center justify-between border-b border-slate-900 px-4 py-3">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
              <Users className="h-4 w-4 text-indigo-400" /> Users
              <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">{users.length}</span>
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-900/60 text-slate-400">
                <tr>
                  <th className="px-4 py-2.5 font-medium">User</th>
                  <th className="px-4 py-2.5 font-medium">Joined</th>
                  <th className="px-4 py-2.5 font-medium text-right">Crawls</th>
                  <th className="px-4 py-2.5 font-medium text-right">Active</th>
                  <th className="px-4 py-2.5 font-medium text-right">URLs</th>
                  <th className="px-4 py-2.5 font-medium">Last crawl</th>
                  <th className="px-4 py-2.5"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-900/70">
                {users.map((u) => (
                  <tr key={u.id} className="transition hover:bg-indigo-500/5">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-500/15 text-[11px] font-bold uppercase text-indigo-300">
                          {u.username.slice(0, 2)}
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 font-medium text-white">
                            {u.username}
                            {u.is_admin && <span className="rounded bg-indigo-500/20 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-indigo-300">admin</span>}
                            {!u.is_active && <span className="rounded bg-red-500/20 px-1.5 py-0.5 text-[9px] font-semibold uppercase text-red-300">disabled</span>}
                          </div>
                          <div className="truncate text-[11px] text-slate-500">{u.email}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-400">{fmt(u.created_at)}</td>
                    <td className="px-4 py-3 text-right font-semibold text-white">{u.total_crawls}</td>
                    <td className="px-4 py-3 text-right">
                      {u.active_crawls > 0
                        ? <span className="inline-flex items-center gap-1 text-indigo-400"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-400" />{u.active_crawls}</span>
                        : <span className="text-slate-600">0</span>}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-slate-300">{u.urls_checked.toLocaleString()}</td>
                    <td className="px-4 py-3 text-slate-400">{fmt(u.last_crawl_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={() => openUser(u)} className="inline-flex items-center gap-1 rounded-lg border border-slate-800 px-2 py-1 text-[11px] text-slate-400 transition hover:border-indigo-500/40 hover:text-indigo-400">
                        <Eye className="h-3 w-3" /> Crawls
                      </button>
                    </td>
                  </tr>
                ))}
                {!loading && users.length === 0 && (
                  <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">No users yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </main>

      {/* Per-user crawls drawer */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={() => setSelected(null)}>
          <div className="max-h-[85vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-slate-800 bg-slate-950 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="sticky top-0 flex items-center justify-between border-b border-slate-900 bg-slate-950/95 px-6 py-4 backdrop-blur">
              <button onClick={() => setSelected(null)} className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white">
                <ChevronLeft className="h-4 w-4" /> Back
              </button>
              <div className="text-right">
                <div className="text-sm font-semibold text-white">{selected.username}</div>
                <div className="text-[11px] text-slate-500">{selected.email}</div>
              </div>
            </div>
            <div className="p-6">
              {loadingCrawls ? (
                <div className="flex items-center gap-2 text-xs text-slate-500"><RotateCw className="h-3.5 w-3.5 animate-spin" /> Loading…</div>
              ) : crawls.length === 0 ? (
                <p className="text-sm text-slate-500">This user hasn't run any crawls.</p>
              ) : (
                <table className="w-full text-left text-xs">
                  <thead className="text-slate-400">
                    <tr>
                      <th className="pb-2 font-medium">Domain</th>
                      <th className="pb-2 font-medium">Status</th>
                      <th className="pb-2 font-medium text-right">Checked</th>
                      <th className="pb-2 font-medium">Started</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-900/70">
                    {crawls.map((c) => (
                      <tr key={c.id}>
                        <td className="py-2.5 font-medium text-white">{c.domain}</td>
                        <td className="py-2.5">
                          <span className={`rounded-full px-2 py-0.5 text-[10px] ${
                            c.status === "completed" ? "bg-emerald-500/10 text-emerald-400" :
                            c.status === "failed" ? "bg-red-500/10 text-red-400" :
                            c.status === "running" || c.status === "pending" ? "bg-indigo-500/10 text-indigo-400" :
                            "bg-slate-800 text-slate-400"}`}>{c.status}</span>
                        </td>
                        <td className="py-2.5 text-right font-mono text-slate-300">{c.total_urls_checked} / {Math.max(c.total_urls_found, c.total_urls_checked)}</td>
                        <td className="py-2.5 text-slate-400">{fmt(c.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ icon: Icon, label, value, sub, tone }: { icon: any; label: string; value?: number; sub?: string; tone?: "indigo" | "green" | "red" }) {
  const color = tone === "green" ? "text-emerald-400" : tone === "red" ? "text-red-400" : tone === "indigo" ? "text-indigo-400" : "text-white";
  return (
    <div className="rounded-xl border border-slate-900 bg-slate-900/40 p-3">
      <Icon className={`h-4 w-4 ${tone ? color : "text-slate-500"}`} />
      <div className={`mt-2 text-xl font-bold ${color}`}>{value === undefined ? "—" : value.toLocaleString()}</div>
      <div className="text-[11px] text-slate-500">{label}</div>
      {sub && <div className="mt-0.5 text-[10px] text-slate-600">{sub}</div>}
    </div>
  );
}
