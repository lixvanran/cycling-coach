// API 客户端
import type {
  ActivityDetail,
  ActivitySummary,
  Athlete,
  CalendarMonth,
  DashboardOverview,
  DiagnoseInfo,
  MockProfile,
  PMCSeries,
  PMCToday,
  PlanPeriod,
  PlanPeriodDetail,
  PlannedWorkout,
} from "./types";

const BASE = "/api"; // 通过 Vite 代理转发到 127.0.0.1:8765

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`HTTP ${r.status}: ${text || r.statusText}`);
  }
  return r.json();
}

export const api = {
  diagnose: () => jsonFetch<DiagnoseInfo>("/diagnose"),

  // 运动员
  getAthlete: () => jsonFetch<Athlete>("/athlete"),
  updateAthlete: (data: Partial<Athlete>) =>
    jsonFetch<Athlete>("/athlete", { method: "PATCH", body: JSON.stringify(data) }),

  // 活动
  listActivities: (params?: {
    date_from?: string;
    date_to?: string;
    min_distance_km?: number;
    max_distance_km?: number;
    min_tss?: number;
    max_tss?: number;
    min_normalized_power?: number;
    max_normalized_power?: number;
    min_avg_power?: number;
    max_avg_power?: number;
    min_duration_min?: number;
    max_duration_min?: number;
    min_avg_hr?: number;
    max_avg_hr?: number;
    source?: string;
    has_report?: boolean;
    sort?: "start_time" | "duration_s" | "tss" | "distance_m" | "avg_power" | "avg_hr" | "normalized_power";
    order?: "asc" | "desc";
    limit?: number;
    offset?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
      });
    }
    return jsonFetch<{
      activities: ActivitySummary[];
      total: number;
      offset: number;
      limit: number;
      aggregate: {
        count: number;
        total_duration_s: number;
        total_tss: number;
        total_distance_m: number;
      };
    }>(`/activities?${sp.toString()}`);
  },
  getActivity: (id: number) => jsonFetch<ActivityDetail>(`/activities/${id}`),
  getPowerCurve: (id: number) =>
    jsonFetch<{
      activity_id: number;
      points: { duration_s: number; watts: number }[];
      ftp_estimate: number | null;
      key_durations: Record<string, number | null>;
      weight_kg: number | null;
    }>(`/activities/${id}/power-curve`),

  // V0.6 GoldenCheetah 对标 — Coggan 7 区详细分布
  getPowerZonesDetailed: (id: number, ftp?: number) => {
    const q = ftp ? `?ftp=${ftp}` : "";
    return jsonFetch<{
      activity_id: number;
      ftp: number;
      total_seconds: number;
      total_distance_km: number;
      total_kj: number;
      zones: Array<{
        code: string; name: string; color: string;
        lo_pct: number; hi_pct: number;
        seconds: number; percent_time: number; percent_distance: number;
        avg_power: number | null; max_power: number | null; kj: number;
      }>;
      summary: {
        polarization_index: number;
        sweet_spot_seconds: number;
        above_ftp_seconds: number;
        easy_seconds: number;
        hard_seconds: number;
      };
    }>(`/activities/${id}/power-zones-detailed${q}`);
  },

  // V0.6 — W'bal 详细分析 (Skiba 模型)
  getWbal: (id: number, cp?: number, wPrime?: number) => {
    const params = new URLSearchParams();
    if (cp) params.set("cp", String(cp));
    if (wPrime) params.set("w_prime", String(wPrime));
    const q = params.toString() ? `?${params.toString()}` : "";
    return jsonFetch<{
      activity_id: number;
      cp: number;
      w_prime: number;
      wbal_curve: number[];
      min_wbal: number; min_wbal_at_s: number; min_wbal_pct: number;
      depleted: boolean; depletion_at_s: number | null;
      critical_events: Array<{ start_s: number; end_s: number; duration_s: number; min_wbal: number; min_wbal_pct: number; }>;
      match_potential: number;
      tau_s: number;
    }>(`/activities/${id}/wbal${q}`);
  },

  // V0.6.1 — Pa:HR Decoupling (心率-功率解耦)
  getDecoupling: (id: number) =>
    jsonFetch<{
      activity_id: number;
      applicable: boolean;
      error?: string;
      actual_samples?: number;
      duration_s?: number;
      decoupling_pct?: number;
      first_half?: { duration_s: number; avg_power: number; avg_hr: number; efficiency_factor: number };
      second_half?: { duration_s: number; avg_power: number; avg_hr: number; efficiency_factor: number };
      interpretation?: "excellent" | "normal" | "high" | "warning";
      interpretation_label?: string;
      color?: string;
      trend?: Array<{ start_s: number; end_s: number; decoupling_pct: number; first_ef: number; second_ef: number }>;
    }>(`/activities/${id}/decoupling`),

  // V0.6 — CP 3 参数自动估算
  getCpEstimate: (id: number) =>
    jsonFetch<{
      activity_id: number;
      cp_estimated?: number; w_prime_estimated?: number;
      method?: string; confidence?: number;
      p60_watts?: number; p180_watts?: number; mmp?: Record<string, number>;
      error?: string;
    }>(`/activities/${id}/cp-estimate`),

  // V0.6.1 — ACWR 急慢性负荷比
  // V0.6.1 FTP 测试 (4 种协议)
  ftpMethods: () => jsonFetch<{ methods: Record<string, any> }>("/ftp/methods"),

  ftpEstimate: (activityId: number, method: string = "auto") =>
    jsonFetch<import("./types").FTPEstimate>("/ftp/estimate", {
      method: "POST",
      body: JSON.stringify({ activity_id: activityId, method }),
    }),

  ftpRecord: (data: any) =>
    jsonFetch<import("./types").FTPTest>("/ftp/test", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  ftpHistory: (days: number = 365) => jsonFetch<import("./types").FTPTest[]>(`/ftp/history?days=${days}`),

  ftpRecommend: () => jsonFetch<import("./types").FTPRecommend>("/ftp/recommend"),

  ftpDelete: (id: number) => jsonFetch<{ ok: boolean; id: number }>(`/ftp/test/${id}`, { method: "DELETE" }),

  // V0.6.1 训练周期 (Periodization)
  phasesMeta: () => jsonFetch<{ phases: Record<string, { label: string; color: string; description: string; icon: string }> }>("/phases/meta"),

  phasesList: () => jsonFetch<import("./types").TrainingPhase[]>("/phases"),

  phasesCurrent: () => jsonFetch<import("./types").TrainingPhase | null>("/phases/current"),

  phasesNextRace: () => jsonFetch<{ id: number; name: string; date: string; days_to_race: number; phase_type: string } | null>("/phases/next-race"),

  phasesSuggest: () => jsonFetch<{
    suggestion: string;
    label: string;
    confidence: number;
    reasons: string[];
    target_weekly_tss: number;
    target_weekly_tss_range: number[];
    weeks_recommended: number;
    weeks_to_race: number | null;
    current_ctl: number;
    current_atl: number;
    current_tsb: number;
    ramp_rate: number;
  }>("/phases/suggest"),

  phasesPolarized: (days: number = 30) =>
    jsonFetch<{
      total_seconds: number;
      total_hours: number;
      zones: Record<string, number>;
      pct: { easy: number; threshold: number; hard: number };
      polarized_score: number;
      interpretation: string;
      target: { easy_pct: number; hard_pct: number; threshold_pct_max: number };
      days_analyzed: number;
    }>(`/phases/polarized?days=${days}`),

  phasesRacePlan: (raceDate: string, raceName: string = "目标比赛") =>
    jsonFetch<{
      race_date: string;
      race_name: string;
      weeks_total: number;
      current_ftp: number;
      current_ctl: number;
      plan: Array<{
        phase: string;
        label: string;
        weeks: number;
        weekly_tss_target: number;
        weekly_tss_range: number[];
        ftp_target: number;
        zone_distribution: Record<string, number>;
        intensity_focus: string;
        key_workouts: string[];
        notes: string;
      }>;
    }>(`/phases/race-plan?race_date=${raceDate}&race_name=${encodeURIComponent(raceName)}`),

  phasesCreate: (data: any) =>
    jsonFetch<import("./types").TrainingPhase>("/phases", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  phasesUpdate: (id: number, data: any) =>
    jsonFetch<import("./types").TrainingPhase>(`/phases/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  phasesDelete: (id: number) => jsonFetch<{ ok: boolean; id: number }>(`/phases/${id}`, { method: "DELETE" }),

  updateRpe: (id: number, rpe: number | null, rpeNote?: string | null) =>
    jsonFetch<{ ok: boolean; activity_id: number; rpe: number | null; rpe_note: string | null }>(`/activities/${id}/rpe`, {
      method: "PATCH",
      body: JSON.stringify({ rpe, rpe_note: rpeNote }),
    }),

  trendsRpe: (days: number) =>
    jsonFetch<{
      series: Array<{ date: string; avg_rpe: number; count: number; tss: number; rpe_tss_ratio: number | null }>;
      overall_avg: number | null;
      high_rpe_days: number;
      low_rpe_days: number;
      days: number;
    }>(`/trends/rpe-trend?days=${days}`),

  trendsAcwr: (days: number) =>
    jsonFetch<{
      today: { date: string; acute: number; chronic: number; acwr: number; zone: string } | null;
      weekly_change: number | null;
      risk: "low" | "medium" | "high";
      risk_label: string;
      recommendation: string;
      series: Array<{ date: string; acute: number; chronic: number; acwr: number; zone: string }>;
      windows: { acute_days: number; chronic_days: number };
    }>(`/trends/acwr?days=${days}`),

  // V0.6 — 长期趋势 (Trends)
  trendsOverview: (days: number) =>
    jsonFetch<{
      days: number;
      weeks: number;
      volume: {
        days: number; bucket: string;
        series: Array<{ key: string; tss: number; distance_km: number; duration_h: number; activities: number }>;
        summary: { total_tss: number; total_distance_km: number; total_duration_h: number; avg_weekly_tss: number; weeks_count: number };
        yoy: { tss_change_pct: number; distance_change_pct: number } | null;
      };
      zones: {
        days: number; bucket: string;
        series: Array<{ key: string; total_seconds: number; Z1: number; Z2: number; Z3: number; Z4: number; Z5: number; Z6: number; Z7: number; Z1_pct: number; Z2_pct: number; Z3_pct: number; Z4_pct: number; Z5_pct: number; Z6_pct: number; Z7_pct: number }>;
      };
      metrics: {
        days: number; bucket: string;
        series: Array<{ key: string; avg_normalized_power: number | null; avg_intensity_factor: number | null; avg_power: number | null; avg_hr: number | null; avg_cadence: number | null; activities: number }>;
      };
      pmc: Array<{ date: string; ctl: number; atl: number; tsb: number; tss: number }>;
      yoy: { tss_change_pct: number; distance_change_pct: number } | null;
    }>(`/trends/overview?days=${days}`),

  // V0.6 — 多活动对比
  compareActivities: (ids: number[]) => {
    const params = new URLSearchParams();
    params.set("ids", ids.join(","));
    return jsonFetch<{
      activities: Array<{
        id: number; name: string; start_time: string | null;
        duration_s: number; duration_str: string;
        distance_km: number; avg_power: number | null; avg_hr: number | null;
        avg_cadence: number | null; tss: number | null; tss_per_hour: number;
        metrics: Record<string, number | null>;
        mmp: Record<string, number>;
        zones: Record<string, number>;
      }>;
      comparison: {
        metrics_table: Array<{ label: string; values: any[] }>;
        best_by_metric: Record<string, number>;
        count: number;
      };
    }>(`/activities/compare?${params.toString()}`);
  },
  uploadActivity: async (file: File, onProgress?: (pct: number) => void) => {
    // 用 XHR 拿真实进度
    return new Promise<{ ok: boolean; id: number; metrics: any }>((resolve, reject) => {
      const form = new FormData();
      form.append("file", file);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", BASE + "/activities/upload");
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText));
          } catch (e) {
            reject(new Error("Bad response: " + xhr.responseText));
          }
        } else {
          reject(new Error(`HTTP ${xhr.status}: ${xhr.responseText}`));
        }
      };
      xhr.onerror = () => reject(new Error("Network error"));
      xhr.send(form);
    });
  },
  analyzeActivity: (id: number, focus?: string) =>
    jsonFetch<{ ok: boolean; report: string | null; reason: string | null }>(
      `/activities/${id}/analyze`,
      { method: "POST", body: JSON.stringify({ focus: focus || null }) }
    ),
  deleteActivity: (id: number) =>
    jsonFetch<{ ok: boolean }>(`/activities/${id}`, { method: "DELETE" }),

  // Dashboard
  getOverview: () => jsonFetch<DashboardOverview>("/dashboard/overview"),

  // PMC (V0.3)
  getPMC: (days = 90) => jsonFetch<PMCSeries>(`/pmc?days=${days}`),
  getPMCToday: () => jsonFetch<PMCToday>("/pmc/today"),
  rebuildPMC: () => jsonFetch<{ ok: boolean; updated_rows: number }>("/pmc/rebuild", { method: "POST" }),

  // Dev(mock)
  listMockProfiles: () =>
    jsonFetch<{ profiles: MockProfile[] }>("/dev/mock-profiles"),
  generateMock: (profileKey: string) =>
    jsonFetch<{ ok: boolean; id: number; name: string; metrics: any }>(
      `/dev/generate-mock?profile_key=${encodeURIComponent(profileKey)}`,
      { method: "POST" }
    ),

  // Plans (V0.3.2)
  listPlans: () => jsonFetch<{ plans: PlanPeriod[] }>("/plans"),
  getPlan: (id: number) => jsonFetch<PlanPeriodDetail>(`/plans/${id}`),
  createPlan: (data: {
    name: string;
    period_type?: string;
    start_date: string;
    end_date: string;
    target_event?: string;
    weekly_hours_target?: number;
    notes?: string;
  }) =>
    jsonFetch<PlanPeriod>("/plans", {
      method: "POST", body: JSON.stringify(data),
    }),
  updatePlan: (id: number, data: Partial<PlanPeriod>) =>
    jsonFetch<PlanPeriod>(`/plans/${id}`, {
      method: "PATCH", body: JSON.stringify(data),
    }),
  deletePlan: (id: number) =>
    jsonFetch<{ ok: boolean; id: number }>(`/plans/${id}`, { method: "DELETE" }),

  // Calendar (V0.3.2)
  getCalendar: (year: number, month: number) =>
    jsonFetch<CalendarMonth>(`/calendar?year=${year}&month=${month}`),
  createPlanned: (data: {
    scheduled_date: string;
    title: string;
    intent?: string;
    duration_target_min?: number;
    tss_target?: number;
    notes?: string;
    period_id?: number;
    workout_id?: number;
  }) =>
    jsonFetch<PlannedWorkout>("/calendar/planned", {
      method: "POST", body: JSON.stringify(data),
    }),
  updatePlanned: (id: number, data: Partial<PlannedWorkout>) =>
    jsonFetch<PlannedWorkout>(`/calendar/planned/${id}`, {
      method: "PATCH", body: JSON.stringify(data),
    }),
  deletePlanned: (id: number) =>
    jsonFetch<{ ok: boolean; id: number }>(`/calendar/planned/${id}`, {
      method: "DELETE",
    }),
  linkPlanned: (plannedId: number, activityId: number) =>
    jsonFetch<PlannedWorkout>(
      `/calendar/planned/${plannedId}/link/${activityId}`,
      { method: "POST" }
    ),
  unlinkPlanned: (plannedId: number) =>
    jsonFetch<PlannedWorkout>(
      `/calendar/planned/${plannedId}/unlink`,
      { method: "POST" }
    ),
  autoLinkMonth: (year: number, month: number) =>
    jsonFetch<{ ok: boolean; linked: number; total: number }>(
      `/calendar/auto-link?year=${year}&month=${month}`,
      { method: "POST" }
    ),

  // AI 教练对话 — SSE 流式
  chatStream: async function* (
    messages: { role: string; content: string }[],
    message: string,
    signal?: AbortSignal
  ): AsyncGenerator<{ type: "text" | "think" | "done" | "error" | "sources"; data: any }> {
    const r = await fetch(BASE + "/coach/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, message }),
      signal,
    });
    if (!r.ok || !r.body) {
      throw new Error(`HTTP ${r.status}: ${await r.text().catch(() => r.statusText)}`);
    }
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE 帧以 \n\n 分隔
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const line = frame.replace(/^data: /, "").trim();
        if (!line) continue;
        if (line === "[DONE]") {
          yield { type: "done", data: "" };
          return;
        }
        if (line.startsWith("[ERROR]")) {
          yield { type: "error", data: line.slice(7).trim() };
          return;
        }
        if (line.startsWith("[SOURCES]")) {
          try {
            const json = line.slice(9).trim().replace(/\\n/g, "\n");
            const sources = JSON.parse(json);
            yield { type: "sources", data: sources };
          } catch (e) {
            // ignore parse error
          }
          continue;
        }
        // unescape \n
        yield { type: "text", data: line.replace(/\\n/g, "\n") };
      }
    }
  },

  // ============== 课程库 (V0.3.3) ==============
  // 注意:jsonFetch 已经会拼 BASE="/api",所以这里只传相对路径 "/workouts"
  listWorkouts: (params?: {
    q?: string;
    goal?: string;
    intensity?: string;
    tag?: string;
    source?: string;
    only_templates?: boolean;
    limit?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params?.q) sp.set("q", params.q);
    if (params?.goal) sp.set("goal", params.goal);
    if (params?.intensity) sp.set("intensity", params.intensity);
    if (params?.tag) sp.set("tag", params.tag);
    if (params?.source) sp.set("source", params.source);
    if (params?.only_templates) sp.set("only_templates", "true");
    if (params?.limit) sp.set("limit", String(params.limit));
    return jsonFetch<{ workouts: import("./types").Workout[]; total: number }>(
      `/workouts?${sp.toString()}`
    );
  },
  getWorkout: (id: number) =>
    jsonFetch<import("./types").Workout>(`/workouts/${id}`),
  listWorkoutTags: () =>
    jsonFetch<{ tags: string[] }>("/workouts/tags"),
  listWorkoutGoals: () =>
    jsonFetch<{ goals: import("./types").GoalDef[] }>("/workouts/goals"),
  createWorkout: (data: Partial<import("./types").Workout>) =>
    jsonFetch<import("./types").Workout>("/workouts", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateWorkout: (id: number, data: Partial<import("./types").Workout>) =>
    jsonFetch<import("./types").Workout>(`/workouts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteWorkout: (id: number) =>
    jsonFetch<{ ok: boolean; id: number }>(`/workouts/${id}`, {
      method: "DELETE",
    }),
  duplicateWorkout: (id: number, newTitle?: string) =>
    jsonFetch<import("./types").Workout>(`/workouts/${id}/duplicate`, {
      method: "POST",
      body: JSON.stringify(newTitle ? { new_title: newTitle } : {}),
    }),
  scheduleWorkout: (id: number, scheduledDate: string, periodId?: number) => {
    const sp = new URLSearchParams({ scheduled_date: scheduledDate });
    if (periodId) sp.set("period_id", String(periodId));
    return jsonFetch<{ planned_id: number; ok: boolean }>(
      `/workouts/${id}/schedule?${sp.toString()}`,
      { method: "POST" }
    );
  },

  // ============== 知识库 (V0.5) ==============
  kbCategories: () =>
    jsonFetch<{ categories: import("./types").KbCategory[]; total: number }>("/kb/categories"),
  kbDocuments: (params?: { path?: string; category_code?: string; limit?: number; offset?: number }) => {
    const sp = new URLSearchParams();
    if (params?.path) sp.set("path", params.path);
    if (params?.category_code) sp.set("category_code", params.category_code);
    if (params?.limit) sp.set("limit", String(params.limit));
    if (params?.offset) sp.set("offset", String(params.offset));
    return jsonFetch<{ documents: import("./types").KbDocumentSummary[]; total: number }>(
      `/kb/documents?${sp.toString()}`
    );
  },
  kbDocument: (id: number) =>
    jsonFetch<import("./types").KbDocument>(`/kb/documents/${id}`),
  kbByPath: (path: string) =>
    jsonFetch<import("./types").KbDocument>(
      `/kb/by-path?path=${encodeURIComponent(path)}`
    ),
  kbSearch: (q: string, limit = 20) =>
    jsonFetch<{
      results: import("./types").KbSearchResult[];
      total: number;
      query: string;
    }>(`/kb/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  kbStats: () => jsonFetch<import("./types").KbStats>("/kb/stats"),
  kbAttachments: (params?: { is_likely_decoration?: boolean; is_visible?: boolean; limit?: number; offset?: number }) => {
    const sp = new URLSearchParams();
    if (params?.is_likely_decoration !== undefined) sp.set("is_likely_decoration", String(params.is_likely_decoration));
    if (params?.is_visible !== undefined) sp.set("is_visible", String(params.is_visible));
    if (params?.limit) sp.set("limit", String(params.limit));
    if (params?.offset) sp.set("offset", String(params.offset));
    return jsonFetch<{ attachments: any[]; total: number }>(`/kb/attachments?${sp.toString()}`);
  },
  kbPatchAttachment: (id: number, payload: { is_visible?: boolean; is_likely_decoration?: boolean }) =>
    jsonFetch<any>(`/kb/attachments/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
};
