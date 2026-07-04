"use client";

import React, { useState, useEffect } from "react";
import axios from "axios";
import { X, CalendarClock, Trash2, RotateCw, CheckCircle2 } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Schedule {
  id: string;
  domain_id: string;
  domain: string;
  frequency: string;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
}

const FREQUENCIES = [
  { value: "hourly", label: "Every hour" },
  { value: "daily", label: "Every day" },
  { value: "weekly", label: "Every week" },
];

export default function ScheduleModal({ jobId, domain, onClose }: { jobId: string; domain: string; onClose: () => void }) {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [frequency, setFrequency] = useState("daily");
  const [saving, setSaving] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadSchedules = async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/crawl/schedules`);
      setSchedules(res.data);
    } catch {
      setError("Failed to load schedules.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadSchedules(); }, []);

  const createSchedule = async () => {
    setSaving(true);
    setError(null);
    try {
      await axios.post(`${API_BASE}/api/crawl/jobs/${jobId}/schedule`, { frequency });
      setJustSaved(true);
      setTimeout(() => setJustSaved(false), 2500);
      await loadSchedules();
    } catch (err: any) {
      setError(err?.response?.data?.message || "Failed to create schedule.");
    } finally {
      setSaving(false);
    }
  };

  const deleteSchedule = async (id: string) => {
    setDeletingId(id);
    try {
      await axios.delete(`${API_BASE}/api/crawl/schedules/${id}`);
      await loadSchedules();
    } catch {
      setError("Failed to delete schedule.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-slate-800 bg-slate-950 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 flex items-start justify-between border-b border-slate-900 bg-slate-950/95 px-6 py-4 backdrop-blur">
          <div className="min-w-0 pr-4">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
              <CalendarClock className="h-4 w-4 text-indigo-400" /> Scheduled Audits
            </h2>
            <p className="mt-1 truncate text-xs text-slate-400">Auto re-crawl domains on a recurring cadence</p>
          </div>
          <button onClick={onClose} className="shrink-0 rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-900 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-6 p-6">
          <div className="space-y-3">
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
              Schedule {domain}
            </label>
            <div className="flex flex-col gap-3 sm:flex-row">
              <select
                value={frequency}
                onChange={(e) => setFrequency(e.target.value)}
                className="flex-1 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none"
              >
                {FREQUENCIES.map((f) => (
                  <option key={f.value} value={f.value}>{f.label}</option>
                ))}
              </select>
              <button
                onClick={createSchedule}
                disabled={saving}
                className="flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-md shadow-indigo-600/25 transition hover:shadow-indigo-500/40 disabled:opacity-50"
              >
                {saving ? <RotateCw className="h-4 w-4 animate-spin" /> : justSaved ? <CheckCircle2 className="h-4 w-4" /> : <CalendarClock className="h-4 w-4" />}
                {justSaved ? "Scheduled" : "Schedule"}
              </button>
            </div>
            <p className="text-[11px] text-slate-500">
              One schedule per domain - scheduling again just changes the cadence. The first run happens one interval from now.
            </p>
            {error && <p className="text-xs text-red-400">{error}</p>}
          </div>

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">Your schedules</h3>
            {loading ? (
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <RotateCw className="h-3.5 w-3.5 animate-spin" /> Loading…
              </div>
            ) : schedules.length === 0 ? (
              <p className="text-xs text-slate-500">No recurring audits yet.</p>
            ) : (
              <div className="divide-y divide-slate-900 rounded-lg border border-slate-800">
                {schedules.map((s) => (
                  <div key={s.id} className="flex items-center justify-between gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-white">{s.domain}</div>
                      <div className="mt-0.5 text-[11px] text-slate-500">
                        {FREQUENCIES.find((f) => f.value === s.frequency)?.label || s.frequency}
                        {s.next_run_at && <> &middot; next run {new Date(s.next_run_at + "Z").toLocaleString()}</>}
                      </div>
                    </div>
                    <button
                      onClick={() => deleteSchedule(s.id)}
                      disabled={deletingId === s.id}
                      title="Remove schedule"
                      className="shrink-0 rounded-lg border border-slate-800 p-1.5 text-slate-500 transition hover:border-red-500/40 hover:text-red-400 disabled:opacity-50"
                    >
                      {deletingId === s.id ? <RotateCw className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
