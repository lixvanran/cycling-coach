// 比赛战术规划 — V0.7.5.10
// 借鉴 TrainingPeaks Race Plan / WKO5 Race Day
// UI: 顶部 session 列表 (卡片), 下方选中 session 详情
//      左侧: 比赛信息 + 路书 + AI 建议
//      右侧: 聊天 + 输入
import { useEffect, useState, useRef, useCallback } from "react";
import {
  Trophy, Plus, Send, Trash2, Upload, FileText, Image as ImageIcon,
  Sparkles, ChevronLeft, Loader2, MapPin, Calendar, Mountain,
  Wind, Layers, AlertCircle, X, CheckCircle2, Download,
} from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
import { useAppStore } from "../store/useAppStore";
import { useToast } from "../components/Toast";
import type {
  RaceTacticsSession, RaceTacticsMessage, RaceTacticsAttachment,
} from "../lib/types";

const RACE_TYPE_LABEL: Record<string, string> = {
  road_race: "公路赛",
  crit: "绕圈赛",
  tt: "计时赛",
  gran_fondo: "长距离/Gran Fondo",
  hill_climb: "爬坡赛",
  stage_race: "多日赛",
};

function formatSize(b: number) {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

export function RaceTacticsPage() {
  const toast = useToast();
  const setView = useAppStore((s) => s.setView);
  const [sessions, setSessions] = useState<RaceTacticsSession[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [session, setSession] = useState<RaceTacticsSession | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sources, setSources] = useState<Array<{ title: string; path: string; snippet: string }>>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // 加载列表
  const loadList = useCallback(async () => {
    try {
      const r = await api.raceTacticsList();
      setSessions(r.items);
    } catch (e: any) {
      toast.error("加载会话列表失败: " + e?.message);
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);

  // 加载选中详情
  useEffect(() => {
    if (!selectedId) { setSession(null); return; }
    api.raceTacticsGet(selectedId).then(setSession).catch(() => setSession(null));
  }, [selectedId]);

  // 滚动到底
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages?.length, streaming]);

  // 创建
  async function createSession(data: Partial<RaceTacticsSession>) {
    try {
      const r = await api.raceTacticsCreate(data);
      toast.success("战术会话已创建");
      setShowCreate(false);
      await loadList();
      setSelectedId(r.session.id);
    } catch (e: any) {
      toast.error("创建失败: " + e?.message);
    }
  }

  // 删除
  async function deleteSession(id: number) {
    if (!confirm("删除该战术会话? 消息和路书都会一起删除.")) return;
    try {
      await api.raceTacticsDelete(id);
      toast.success("已删除");
      if (selectedId === id) setSelectedId(null);
      await loadList();
    } catch (e: any) {
      toast.error("删除失败: " + e?.message);
    }
  }

  // 发送消息 (SSE)
  async function send(content: string) {
    if (!selectedId || !content.trim()) return;
    setInput("");
    setStreaming(true);
    setSources([]);

    // 乐观更新: 加 user + 占位 assistant
    const userMsg: RaceTacticsMessage = {
      id: Date.now(), role: "user", content, thinking: null, rag_sources: [], created_at: new Date().toISOString(),
    };
    const asstMsg: RaceTacticsMessage = {
      id: Date.now() + 1, role: "assistant", content: "", thinking: null, rag_sources: [], created_at: new Date().toISOString(),
    };
    setSession((s) => s ? { ...s, messages: [...(s.messages || []), userMsg, asstMsg] } : s);

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    let fullText = "";
    try {
      const resp = await fetch(`/api/race-tactics/sessions/${selectedId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
        signal: ctrl.signal,
      });
      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6);
            if (data === "[DONE]") {
              setStreaming(false);
              // 重载消息拿最终 ID + RAG
              api.raceTacticsGet(selectedId).then(setSession).catch(() => {});
              return;
            }
            if (data.startsWith("[SOURCES] ")) {
              try {
                setSources(JSON.parse(data.slice(10)));
              } catch {}
              continue;
            }
            if (data.startsWith("[ERROR]")) {
              toast.error(data.replace("[ERROR] ", ""));
              continue;
            }
            fullText += data;
            setSession((s) => {
              if (!s) return s;
              const msgs = [...(s.messages || [])];
              const last = msgs[msgs.length - 1];
              if (last && last.role === "assistant") {
                msgs[msgs.length - 1] = { ...last, content: fullText };
              }
              return { ...s, messages: msgs };
            });
          }
        }
      }
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        toast.error("发送失败: " + e?.message);
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  // AI 自动建议
  async function aiSuggest() {
    if (!selectedId) return;
    setStreaming(true);
    setSources([]);
    const asstMsg: RaceTacticsMessage = {
      id: Date.now(), role: "assistant", content: "🤔 正在思考战术...\n\n", thinking: null, rag_sources: [], created_at: new Date().toISOString(),
    };
    setSession((s) => s ? { ...s, messages: [...(s.messages || []), asstMsg] } : s);

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    let fullText = "";
    try {
      const resp = await fetch(`/api/race-tactics/sessions/${selectedId}/suggest`, {
        method: "POST", signal: ctrl.signal,
      });
      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6);
            if (data === "[DONE]") {
              setStreaming(false);
              api.raceTacticsGet(selectedId).then(setSession).catch(() => {});
              return;
            }
            if (data.startsWith("[SOURCES] ")) {
              try { setSources(JSON.parse(data.slice(10))); } catch {}
              continue;
            }
            if (data.startsWith("[ERROR]")) {
              toast.error(data.replace("[ERROR] ", ""));
              continue;
            }
            fullText += data;
            setSession((s) => {
              if (!s) return s;
              const msgs = [...(s.messages || [])];
              const last = msgs[msgs.length - 1];
              if (last && last.role === "assistant") {
                msgs[msgs.length - 1] = { ...last, content: fullText };
              }
              return { ...s, messages: msgs };
            });
          }
        }
      }
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        toast.error("生成失败: " + e?.message);
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  // 上传路书
  async function uploadFile(file: File) {
    if (!selectedId) return;
    try {
      await api.raceTacticsUpload(selectedId, file);
      toast.success(`已上传 ${file.name}`);
      const r = await api.raceTacticsGet(selectedId);
      setSession(r);
    } catch (e: any) {
      toast.error("上传失败: " + e?.message);
    }
  }

  // 停止
  function stopStream() {
    abortRef.current?.abort();
    setStreaming(false);
  }

  return (
    <div className="h-full flex flex-col bg-bg-base">
      {/* 顶部 */}
      <div className="flex-shrink-0 bg-white/80 backdrop-blur border-b border-border px-5 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg flex items-center justify-center"
            style={{ background: "linear-gradient(135deg, #f59e0b 0%, #ef4444 100%)" }}>
            <Trophy size={18} className="text-white" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-text-primary">比赛战术规划</h1>
            <p className="text-xs text-text-muted">跟 AI 教练商讨比赛战术, 上传路书分析, 引用训练百科</p>
          </div>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-3 py-1.5 text-sm bg-accent text-white rounded-md font-medium hover:opacity-90 flex items-center gap-1.5"
        >
          <Plus size={14} /> 新建战术
        </button>
      </div>

      <div className="flex-1 flex min-h-0">
        {/* 左侧: 列表 */}
        <div className="w-72 flex-shrink-0 border-r border-border bg-bg-elevated/30 overflow-y-auto">
          <div className="p-3">
            {sessions.length === 0 && (
              <div className="text-xs text-text-muted text-center py-8">
                还没有战术会话<br />点右上角"新建战术"
              </div>
            )}
            {sessions.map((s) => (
              <div
                key={s.id}
                onClick={() => setSelectedId(s.id)}
                className={clsx(
                  "p-3 mb-2 rounded-lg cursor-pointer border-2 transition-all",
                  selectedId === s.id
                    ? "bg-accent/10 border-accent/40"
                    : "bg-white border-transparent hover:border-border"
                )}
              >
                <div className="flex items-start justify-between gap-2 mb-1">
                  <div className="text-sm font-semibold text-text-primary truncate flex-1">
                    {s.race_name}
                  </div>
                  {s.priority && (
                    <span className={clsx("text-[9px] px-1.5 py-0.5 rounded font-bold flex-shrink-0",
                      s.priority === "A" ? "bg-red-100 text-red-700" :
                      s.priority === "B" ? "bg-amber-100 text-amber-700" :
                      "bg-gray-100 text-gray-600"
                    )}>
                      {s.priority}
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-text-muted flex items-center gap-2">
                  {s.distance_km && <span>{s.distance_km}km</span>}
                  {s.elevation_gain_m && <span>↑{s.elevation_gain_m}m</span>}
                  <span>·</span>
                  <span>{s.message_count} 消息</span>
                  {s.attachment_count > 0 && <span>· {s.attachment_count} 附件</span>}
                </div>
                {s.race_type && (
                  <div className="text-[10px] text-text-muted mt-1">
                    {RACE_TYPE_LABEL[s.race_type] || s.race_type}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* 右侧: 详情 / 空状态 */}
        {selectedId && session ? (
          <div className="flex-1 flex min-w-0">
            {/* 中间: 比赛信息 + 路书 */}
            <div className="w-80 flex-shrink-0 border-r border-border overflow-y-auto bg-bg-card/30 p-4 space-y-3">
              <div>
                <div className="text-xs text-text-muted mb-1">比赛名称</div>
                <div className="text-sm font-semibold text-text-primary">{session.race_name}</div>
              </div>
              {session.race_date && (
                <div className="flex items-center gap-2 text-xs text-text-secondary">
                  <Calendar size={12} /> {new Date(session.race_date).toLocaleString("zh-CN")}
                </div>
              )}
              {session.distance_km && (
                <div className="flex items-center gap-2 text-xs text-text-secondary">
                  <MapPin size={12} /> {session.distance_km} km
                </div>
              )}
              {session.elevation_gain_m && (
                <div className="flex items-center gap-2 text-xs text-text-secondary">
                  <Mountain size={12} /> 爬升 {session.elevation_gain_m} m
                </div>
              )}
              {session.weather_forecast && (
                <div className="flex items-center gap-2 text-xs text-text-secondary">
                  <Wind size={12} /> {session.weather_forecast}
                </div>
              )}
              {session.course_profile && (
                <div>
                  <div className="text-xs text-text-muted mb-1 mt-2">路线描述</div>
                  <div className="text-xs text-text-secondary whitespace-pre-line">{session.course_profile}</div>
                </div>
              )}

              {/* 路书 */}
              <div className="pt-3 border-t border-border">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs font-semibold text-text-primary">路书附件</div>
                  <label className="cursor-pointer text-xs text-accent hover:underline flex items-center gap-1">
                    <Upload size={11} /> 上传
                    <input
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg,.webp"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) uploadFile(f);
                        e.target.value = "";
                      }}
                    />
                  </label>
                </div>
                {(!session.attachments || session.attachments.length === 0) && (
                  <div className="text-[10px] text-text-muted text-center py-3 border border-dashed border-border rounded">
                    无附件<br />支持 PDF/PNG/JPG/WEBP
                  </div>
                )}
                <div className="space-y-1.5">
                  {session.attachments?.map((a) => (
                    <a
                      key={a.id}
                      href={a.url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-2 p-2 bg-bg-elevated rounded text-xs hover:bg-accent/10 transition-colors group"
                    >
                      {a.mime_type.startsWith("image/") ? <ImageIcon size={14} className="text-text-muted" /> : <FileText size={14} className="text-text-muted" />}
                      <div className="flex-1 min-w-0">
                        <div className="truncate text-text-primary">{a.file_name}</div>
                        <div className="text-[9px] text-text-muted">{formatSize(a.size_bytes)}</div>
                      </div>
                      <Download size={11} className="text-text-muted opacity-0 group-hover:opacity-100" />
                    </a>
                  ))}
                </div>
              </div>

              {/* AI 战术建议 */}
              {session.final_strategy && (
                <div className="pt-3 border-t border-border">
                  <div className="text-xs font-semibold text-text-primary mb-1.5 flex items-center gap-1">
                    <Sparkles size={12} className="text-amber-500" /> 最终战术
                  </div>
                  <div className="text-xs text-text-secondary whitespace-pre-line max-h-48 overflow-y-auto">
                    {session.final_strategy}
                  </div>
                </div>
              )}

              <div className="pt-3 border-t border-border flex gap-2">
                <button
                  onClick={() => aiSuggest()}
                  disabled={streaming}
                  className="flex-1 text-xs px-2 py-1.5 bg-amber-100 text-amber-800 rounded font-medium hover:bg-amber-200 disabled:opacity-50 flex items-center justify-center gap-1"
                >
                  <Sparkles size={11} /> AI 建议
                </button>
                <button
                  onClick={() => deleteSession(session.id)}
                  className="text-xs px-2 py-1.5 text-red-600 hover:bg-red-50 rounded flex items-center gap-1"
                >
                  <Trash2 size={11} /> 删除
                </button>
              </div>
            </div>

            {/* 聊天 */}
            <div className="flex-1 flex flex-col min-w-0">
              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {(!session.messages || session.messages.length === 0) && (
                  <div className="text-center text-text-muted text-sm py-12">
                    跟 AI 教练开始讨论战术<br />
                    <button
                      onClick={() => aiSuggest()}
                      className="mt-3 px-4 py-2 bg-amber-100 text-amber-800 rounded-md text-sm font-medium hover:bg-amber-200"
                    >
                      <Sparkles size={12} className="inline mr-1" /> AI 给我一个建议
                    </button>
                  </div>
                )}
                {session.messages?.map((m) => (
                  <div
                    key={m.id}
                    className={clsx("flex gap-2", m.role === "user" ? "justify-end" : "justify-start")}
                  >
                    {m.role === "assistant" && (
                      <div className="w-7 h-7 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
                        <Trophy size={12} className="text-amber-600" />
                      </div>
                    )}
                    <div
                      className={clsx(
                        "max-w-[75%] px-3 py-2 rounded-lg text-sm whitespace-pre-wrap",
                        m.role === "user"
                          ? "bg-accent text-white"
                          : "bg-bg-elevated text-text-primary"
                      )}
                    >
                      {m.content}
                    </div>
                  </div>
                ))}
                {streaming && (
                  <div className="flex gap-2">
                    <div className="w-7 h-7 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
                      <Loader2 size={12} className="text-amber-600 animate-spin" />
                    </div>
                    <div className="text-xs text-text-muted py-2">思考中...</div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* RAG 来源 */}
              {sources.length > 0 && (
                <div className="border-t border-border px-4 py-2 bg-bg-card/50">
                  <div className="text-[10px] text-text-muted mb-1">📚 参考训练百科</div>
                  <div className="flex flex-wrap gap-1">
                    {sources.map((s, i) => (
                      <span key={i} className="text-[10px] px-2 py-0.5 bg-amber-100 text-amber-800 rounded-full" title={s.snippet}>
                        {s.title}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 输入 */}
              <div className="border-t border-border p-3 flex gap-2">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey && !streaming) {
                      e.preventDefault();
                      send(input);
                    }
                  }}
                  rows={2}
                  placeholder="问 AI 教练: 比赛配速怎么分? 补给节奏? 关键节点策略? (Enter 发送, Shift+Enter 换行)"
                  className="flex-1 px-3 py-2 text-sm border border-border rounded-md bg-bg-elevated resize-none"
                />
                <div className="flex flex-col gap-1">
                  {streaming ? (
                    <button
                      onClick={stopStream}
                      className="px-3 py-1.5 text-xs bg-red-500 text-white rounded-md font-medium hover:opacity-90 flex items-center gap-1"
                    >
                      <X size={12} /> 停止
                    </button>
                  ) : (
                    <button
                      onClick={() => send(input)}
                      disabled={!input.trim()}
                      className="px-3 py-1.5 text-xs bg-accent text-white rounded-md font-medium hover:opacity-90 disabled:opacity-50 flex items-center gap-1"
                    >
                      <Send size={12} /> 发送
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-text-muted text-sm">
            <div className="text-center">
              <Trophy size={48} className="mx-auto mb-3 opacity-20" />
              <div>从左侧选一个比赛, 或新建战术会话</div>
            </div>
          </div>
        )}
      </div>

      {/* 创建对话框 */}
      {showCreate && (
        <CreateSessionDialog
          onClose={() => setShowCreate(false)}
          onCreate={createSession}
        />
      )}
    </div>
  );
}

function CreateSessionDialog({ onClose, onCreate }: {
  onClose: () => void;
  onCreate: (data: Partial<RaceTacticsSession>) => void;
}) {
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [distance, setDistance] = useState("");
  const [elevation, setElevation] = useState("");
  const [type, setType] = useState("road_race");
  const [priority, setPriority] = useState("B");
  const [weather, setWeather] = useState("");
  const [profile, setProfile] = useState("");

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-lg w-full p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-text-primary">新建比赛战术</h2>
          <button onClick={onClose}><X size={16} className="text-text-muted" /></button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <div className="text-xs text-text-muted mb-1">比赛名称 *</div>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="如: 环青海湖 2026 业余组"
              className="w-full px-3 py-2 text-sm border border-border rounded bg-bg-elevated" />
          </div>
          <div>
            <div className="text-xs text-text-muted mb-1">比赛日期</div>
            <input type="datetime-local" value={date} onChange={(e) => setDate(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-border rounded bg-bg-elevated" />
          </div>
          <div>
            <div className="text-xs text-text-muted mb-1">优先级</div>
            <select value={priority} onChange={(e) => setPriority(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-border rounded bg-bg-elevated">
              <option value="A">A (最重要)</option>
              <option value="B">B (重要)</option>
              <option value="C">C (次要)</option>
            </select>
          </div>
          <div>
            <div className="text-xs text-text-muted mb-1">距离 (km)</div>
            <input type="number" value={distance} onChange={(e) => setDistance(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-border rounded bg-bg-elevated" />
          </div>
          <div>
            <div className="text-xs text-text-muted mb-1">爬升 (m)</div>
            <input type="number" value={elevation} onChange={(e) => setElevation(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-border rounded bg-bg-elevated" />
          </div>
          <div className="col-span-2">
            <div className="text-xs text-text-muted mb-1">比赛类型</div>
            <select value={type} onChange={(e) => setType(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-border rounded bg-bg-elevated">
              {Object.entries(RACE_TYPE_LABEL).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
          <div className="col-span-2">
            <div className="text-xs text-text-muted mb-1">天气预报 (选填)</div>
            <input value={weather} onChange={(e) => setWeather(e.target.value)} placeholder="如: 晴 15-25°C 西风 3 级"
              className="w-full px-3 py-2 text-sm border border-border rounded bg-bg-elevated" />
          </div>
          <div className="col-span-2">
            <div className="text-xs text-text-muted mb-1">路线描述 (选填)</div>
            <textarea value={profile} onChange={(e) => setProfile(e.target.value)} rows={3}
              placeholder="如: Day1 平路 100km, Day2 山地 130km, Day3 综合 130km..."
              className="w-full px-3 py-2 text-sm border border-border rounded bg-bg-elevated resize-none" />
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-text-muted">取消</button>
          <button
            onClick={() => {
              if (!name.trim()) { alert("请填写比赛名称"); return; }
              onCreate({
                race_name: name,
                race_date: date ? new Date(date).toISOString() : null,
                distance_km: distance ? parseFloat(distance) : null,
                elevation_gain_m: elevation ? parseInt(elevation) : null,
                race_type: type, priority,
                weather_forecast: weather || null,
                course_profile: profile || null,
              });
            }}
            className="px-4 py-1.5 text-sm bg-accent text-white rounded font-medium hover:opacity-90"
          >
            创建
          </button>
        </div>
      </div>
    </div>
  );
}
