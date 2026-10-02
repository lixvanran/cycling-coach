// 导入页(FIT 上传 + Mock 数据生成) — V0.8.2
// 改动:
//   U-15 重复检测: 上传后查最近 50 条活动, 匹配同日期 + 接近时长
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Upload, Zap, FileUp, Check, AlertTriangle } from "lucide-react";
import { api } from "../lib/api";
import { useToast } from "../components/Toast";
import type { MockProfile } from "../lib/types";

export function ImportPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ id: number; name?: string; duplicateOf?: number } | null>(null);
  const [mockProfiles, setMockProfiles] = useState<MockProfile[]>([]);
  const [generating, setGenerating] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.listMockProfiles().then((d) => setMockProfiles(d.profiles));
  }, []);

  // U-15: 上传后查重 (按日期 + 时长, 客户端简单实现)
  const checkDuplicate = async (newId: number): Promise<number | undefined> => {
    try {
      const a = await api.getActivity(newId);
      if (!a) return undefined;
      const newDate = (a.start_time || "").slice(0, 10);
      const newDur = a.duration_s || 0;
      if (!newDate) return undefined;
      // 查最近 50 条
      const r = await api.listActivities({ limit: 50, sort: "start_time", order: "desc" });
      for (const act of r.activities || []) {
        if (act.id === newId) continue;
        const actDate = (act.start_time || "").slice(0, 10);
        const actDur = act.duration_s || 0;
        if (actDate === newDate && Math.abs(actDur - newDur) < 60) {
          return act.id;
        }
      }
    } catch {
      // 静默失败, 不阻塞主流程
    }
    return undefined;
  };

  const onUpload = async (file: File) => {
    const allowed = [".fit", ".tcx", ".csv"];
    const ext = "." + file.name.toLowerCase().split(".").pop();
    if (!allowed.includes(ext)) {
      toast.error(`不支持的格式: ${ext}\n支持: .fit / .tcx / .csv (WKO/GoldenCheetah)`);
      return;
    }
    setUploading(true);
    setProgress(0);
    setUploadResult(null);
    try {
      const r = await api.uploadActivity(file, setProgress);
      const dup = await checkDuplicate(r.id);
      if (dup != null) {
        toast.warn(`检测到相似活动 (id=${dup}), 可能是重复上传`, { ttl: 5000 });
      }
      setUploadResult({ id: r.id, duplicateOf: dup });
    } catch (e) {
      toast.error("上传失败:" + (e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) onUpload(file);
  };

  const onGenerateMock = async (key: string) => {
    setGenerating(key);
    try {
      const r = await api.generateMock(key);
      setUploadResult({ id: r.id, name: r.name });
      // V0.8.0: 跳转到详情页
      navigate(`/training/activities/${r.id}`);
    } catch (e) {
      toast.error("生成失败:" + (e as Error).message);
    } finally {
      setGenerating(null);
    }
  };

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      <div>
        <h1 className="text-2xl font-semibold text-text-primary">导入训练</h1>
        <p className="text-sm text-text-muted mt-1">
          上传 .fit / .tcx / .csv (WKO/GoldenCheetah) 文件,或者用模拟数据先体验。
        </p>
      </div>

      {/* 上传区 */}
      <section>
        <div
          onDrop={onDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => fileInputRef.current?.click()}
          className="panel border-dashed border-2 hover:border-accent-primary cursor-pointer transition-colors p-10 text-center"
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".fit,.tcx,.csv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onUpload(f);
            }}
          />
          {uploading ? (
            <>
              <div className="text-sm text-text-primary mb-2">上传中... {progress}%</div>
              <div className="w-64 mx-auto h-1.5 bg-bg-subtle rounded-full overflow-hidden">
                <div
                  className="h-full bg-accent-primary transition-all"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </>
          ) : (
            <>
              <FileUp size={32} className="text-text-muted mx-auto mb-3" />
              <div className="text-text-primary mb-1">拖拽 .fit 文件到这里</div>
              <div className="text-xs text-text-muted">或点击选择文件</div>
            </>
          )}
        </div>

        {uploadResult && (
          <div className="mt-3 panel p-3 space-y-2">
            <div className="flex items-center gap-2 text-sm">
              <Check size={14} className="text-accent-success" />
              <span className="text-text-primary">
                {uploadResult.name || "上传成功"}
              </span>
              <button
                onClick={() => navigate(`/training/activities/${uploadResult.id}`)}
                className="ml-auto btn-ghost text-accent-primary"
              >
                查看分析 →
              </button>
            </div>
            {uploadResult.duplicateOf != null && (
              <div className="text-xs text-accent-warning flex items-center gap-1.5 bg-status-warning -mx-3 px-3 py-1.5 border-y border-border">
                <AlertTriangle size={12} className="flex-shrink-0" />
                <span>检测到相似活动 (id={uploadResult.duplicateOf}), 可能是重复上传</span>
                <button
                  onClick={() => navigate(`/training/activities/${uploadResult.duplicateOf}`)}
                  className="ml-auto underline hover:no-underline"
                >
                  查看已有 →
                </button>
              </div>
            )}
            <div className="text-xs text-accent-warning flex items-center gap-1.5 pt-1 border-t border-border">
              <span>⏰</span>
              <span>训练后 30 分钟内最准 — 看完分析后顺手记一下 <span className="font-semibold">RPE 主观疲劳</span></span>
            </div>
          </div>
        )}
      </section>

      {/* Mock 数据 */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-sm uppercase tracking-wider text-text-secondary">
              模拟数据(开发体验)
            </h2>
            <p className="text-xs text-text-muted mt-1">
              没有 FIT 文件?点一下生成示例训练,看完整体验。
            </p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {mockProfiles.map((p) => (
            <div
              key={p.key}
              onClick={() => onGenerateMock(p.key)}
              className="panel p-4 cursor-pointer hover:border-accent-primary transition-colors flex items-center gap-3"
            >
              <div className="w-10 h-10 rounded-md bg-accent-primary/20 flex items-center justify-center">
                <Zap size={18} className="text-accent-primary" />
              </div>
              <div className="flex-1">
                <div className="text-sm font-medium text-text-primary">{p.name}</div>
                <div className="text-xs text-text-muted mt-0.5">key: {p.key}</div>
              </div>
              {generating === p.key ? (
                <div className="text-xs text-text-muted">生成中...</div>
              ) : (
                <Upload size={14} className="text-text-muted" />
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
