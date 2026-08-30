// 共享类型(对齐后端 schema)
export interface ActivitySummary {
  id: number;
  start_time: string;
  duration_s: number;
  distance_m: number | null;
  avg_power: number | null;
  normalized_power: number | null;
  tss: number | null;
  avg_hr: number | null;
  avg_cadence: number | null;
  total_elevation_gain: number | null;
  device: string | null;
  source: string;
  has_report: boolean;
  rpe: number | null;  // V0.6.1 Borg CR-10 (1-10)
  rpe_note: string | null;
}

export interface Sample {
  t_offset: number;
  power: number | null;
  hr: number | null;
  cadence: number | null;
  speed: number | null;
  elevation: number | null;
  lat?: number | null;
  lon?: number | null;
  position_lat?: number | null;
  position_long?: number | null;
}

export interface Lap {
  start_offset: number;
  duration_s: number;
  avg_power: number | null;
  avg_hr: number | null;
  avg_cadence: number | null;
  max_power: number | null;
  max_hr: number | null;
  label: string | null;
  trigger: string | null;
}

export interface ActivityMetrics {
  normalized_power: number | null;
  intensity_factor: number | null;
  tss: number | null;
  efficiency_factor: number | null;
  variability_index: number | null;
  power_curve: Record<string, number>;
  power_zones: Record<string, number>;
  hr_zones: Record<string, number>;
  hr_drift: number | null;
  cadence_zones: Record<string, number>;
  ftp_estimated: number | null;
}

export interface ActivityDetail extends ActivitySummary {
  max_power: number | null;
  max_hr: number | null;
  max_speed: number | null;
  calories: number | null;
  metrics: ActivityMetrics | null;
  samples: Sample[];
  laps: Lap[];
  report: string | null;
  report_status: string;
}

export interface Athlete {
  id: number;
  name: string;
  ftp: number | null;
  ftp_estimated: number | null;
  max_hr: number | null;
  lthr: number | null;
  weight_kg: number | null;
  height_cm: number | null;
  total_activities: number;
  weekly_tss: number;
}

export interface DashboardOverview {
  total_activities: number;
  total_distance_km: number;
  total_duration_h: number;
  total_tss: number;
  this_week: {
    activities: number;
    distance_km: number;
    duration_h: number;
    tss: number;
  };
  last_7_days: Array<{
    date: string;
    tss: number;
    distance_km: number;
    duration_h: number;
  }>;
}

export interface MockProfile {
  key: string;
  name: string;
}

export interface DiagnoseInfo {
  ok: boolean;
  version: string;
  m3_mock_mode: boolean;
  m3_model: string;
  python: string;
  system: string;
}

// ====== PMC (Performance Management Chart) ======
export interface PMCSnapshot {
  date: string;          // ISO date
  tss: number;           // 当日总 TSS
  activity_count: number;
  duration_s: number;
  ctl: number;           // 慢性负荷 (42d EWMA)
  atl: number;           // 急性负荷 (7d EWMA)
  tsb: number;           // TSB = CTL - ATL
  ramp_rate: number;     // 7d CTL 斜率 (TSS/wk)
}

export interface PMCSeries {
  athlete_id: number;
  days: number;
  series: PMCSnapshot[];
}

export type PMCStatusCode =
  | "overtraining"   // 红
  | "taper"          // 蓝
  | "tired"          // 黄
  | "fresh"          // 绿(巅峰)
  | "good"           // 绿(良好)
  | "neutral";       // 黄(无数据/平衡)

export interface PMCToday {
  date: string;
  tss_today: number;
  ctl: number;
  atl: number;
  tsb: number;
  ramp_rate: number;
  status: PMCStatusCode;
  status_label: string;
  status_color: "green" | "yellow" | "red" | "blue";
}

// ====== Plans & Calendar ======
export type PeriodType = "base" | "build" | "peak" | "taper" | "recovery" | "race";
export type WorkoutIntent =
  | "recovery"
  | "endurance"
  | "tempo"
  | "threshold"
  | "vo2max"
  | "race";
export type PlannedStatus = "planned" | "done" | "skipped" | "moved";

export interface PlanPeriod {
  id: number;
  name: string;
  period_type: PeriodType;
  start_date: string;
  end_date: string;
  target_event: string | null;
  weekly_hours_target: number | null;
  notes: string | null;
  workout_count: number;
  created_at: string | null;
}

export interface PlanPeriodDetail extends PlanPeriod {
  workouts: PlannedWorkout[];
}

export interface PlannedWorkout {
  id: number;
  period_id: number | null;
  workout_id: number | null;
  actual_activity_id: number | null;
  scheduled_date: string;
  title: string;
  intent: WorkoutIntent;
  duration_target_min: number | null;
  tss_target: number | null;
  notes: string | null;
  status: PlannedStatus;
  completed_at: string | null;
  created_at?: string | null;
}

export interface ActualActivity {
  id: number;
  title: string;
  duration_s: number;
  distance_m: number | null;
  avg_power: number | null;
  avg_hr: number | null;
  tss: number | null;
  start_time: string;
}

export interface CalendarMonth {
  year: number;
  month: number;
  month_label: string;
  weeks: number[][];         // 6×7
  planned_by_day: Record<string, PlannedWorkout[]>;
  actual_by_day: Record<string, ActualActivity[]>;
  stats: {
    planned_count: number;
    done_count: number;
    skipped_count: number;
    completion_rate: number;
    actual_activities: number;
    actual_tss_total: number;
    actual_hours_total: number;
  };
}

// ============== 课程库 (V0.3.3) ==============

export type WorkoutGoal =
  | "recovery"
  | "endurance"
  | "tempo"
  | "threshold"
  | "vo2max"
  | "race";

export type WorkoutIntensity = WorkoutGoal; // 同 goal

export type WorkoutSource = "system" | "user" | "ai";
export type StepKind = "warmup" | "main" | "recovery" | "cooldown";

export interface WorkoutStep {
  kind: StepKind;
  duration_s: number;
  power_pct_ftp?: number;
  hr_pct_lthr?: number;
  cadence_rpm?: number;
  label?: string;
  repeat?: number;
}

export interface Workout {
  id: number;
  athlete_id: number | null;
  activity_id: number | null;
  title: string;
  goal: WorkoutGoal;
  intensity: WorkoutIntensity | null;
  duration_min: number;
  structure: WorkoutStep[] | null;
  source: WorkoutSource;
  tags: string[];
  is_template: boolean;
  description: string | null;
  erg_text: string | null;
  zwo_text: string | null;
  rationale: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface GoalDef {
  key: WorkoutGoal;
  label: string;
  color: string;
}

// ============== 知识库 (V0.5) ==============

export interface KbCategory {
  id: number;
  code: string;
  name: string;
  parent_code: string | null;
  path: string;
  depth: number;
  doc_count: number;
}

export interface KbDocumentSummary {
  id: number;
  path: string;
  title: string;
  depth: number;
  parent_path: string | null;
  chunk_count: number;
  attachment_count: number;
}

export interface KbAttachment {
  id: number;
  filename: string;
  alt_text: string | null;
  mime_type: string | null;
  size_bytes: number;
  is_likely_decoration: boolean;
  image_url: string;
}

export interface KbDocument {
  id: number;
  path: string;
  title: string;
  depth: number;
  parent_path: string | null;
  category_code: string;
  content_md: string | null;
  content_text: string;
  chunk_count: number;
  attachment_count: number;
  attachments: KbAttachment[];
}

export interface KbSearchResult {
  chunk_id: number;
  document_id: number;
  document_path: string;
  document_title: string;
  chunk_index: number;
  snippet: string;
  content: string;
}

export interface KbStats {
  categories: number;
  documents: number;
  chunks: number;
  attachments: number;
  attachments_visible: number;
  attachments_likely_decoration: number;
}

export interface TrainingPhase {
  id: number;
  phase_type: string;
  name: string;
  start_date: string;
  end_date: string;
  target_tss_week: number | null;
  target_ftp_w: number | null;
  notes: string | null;
  is_race: boolean;
  duration_days: number;
  actual_avg_tss_week: number | null;
  actual_count: number;
}

export interface PhaseMeta {
  label: string;
  color: string;
  description: string;
  icon: string;
}

export interface FTPTest {
  id: number;
  test_date: string;
  method: string;
  method_label: string;
  ftp_w: number;
  confidence: number;
  hr_bpm: number | null;
  weight_kg: number | null;
  w_per_kg: number | null;
  notes: string | null;
  source_activity_id: number | null;
  cp_w: number | null;
  w_prime_kj: number | null;
  days_since: number;
  ftp_change_w: number | null;
  ftp_change_pct: number | null;
}

export interface FTPEstimate {
  method: string;
  method_label: string;
  ftp_w: number;
  confidence: number;
  notes: string[];
  details: Record<string, any>;
  source_activity_id: number | null;
  activity_summary?: {
    id: number;
    start_time: string | null;
    duration_min: number;
    distance_km: number;
    avg_power: number | null;
  };
}

export interface FTPRecommend {
  days_since: number | null;
  should_test: boolean;
  reason: string;
  recommended_method: string;
  priority: "low" | "medium" | "high";
  last_ftp_w?: number;
  last_method?: string;
  last_test_date?: string;
  avg_if_last_14d?: number | null;
}

export interface Insight {
  id: string;
  category: "load" | "recovery" | "race" | "phase" | "ftp" | "distribution";
  severity: "info" | "warning" | "alert";
  title: string;
  description: string;
  recommendation: string;
  metric_value: string | null;
  academic_source: string | null;
}

export interface InsightsToday {
  generated_at: string;
  athlete_id: number;
  summary: {
    total: number;
    alert: number;
    warning: number;
    info: number;
    health_score: number;
    health_label: string;
  };
  pcm: { ctl: number; atl: number; tsb: number; ramp_rate: number };
  insights: Insight[];
}

export interface WeeklyReview {
  this_week: {
    tss: number;
    distance_km: number;
    duration_h: number;
    count: number;
    avg_rpe: number | null;
    zone_pct: Record<string, number>;
    total_zone_seconds: number;
  };
  last_week: {
    tss: number;
    distance_km: number;
    duration_h: number;
    count: number;
    avg_rpe: number | null;
  };
  comparison: { tss_change: number; tss_change_pct: number | null };
  next_week_advice: string;
  ftp_used: number;
}

// V0.7.4.2 训练日记
export interface Diary {
  id: number;
  date: string; // YYYY-MM-DD
  training_feel: number | null; // 1-5
  mood: number | null; // 1-5
  sleep_h: number | null;
  sleep_quality: number | null; // 1-5
  content: string | null;
  weather: string | null;
  equipment_notes: string | null;
  pain_notes: string | null;
  activity_id: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface DiaryTemplateField {
  key: string;
  label: string;
  type: "rating" | "number" | "text" | "textarea" | "activity";
  min?: number;
  max?: number;
  scale?: string;
  tip: string;
}

export interface DiaryTemplate {
  title: string;
  source: string;
  fields: DiaryTemplateField[];
  prompts: string[];
  daily_factors: string[];
}
