// 导入页(FIT 上传 + Mock 数据生成)
import { useEffect, useRef, useState } from "react";
import { Upload, Zap, FileUp, Check } from "lucide-react";
import { api } from "../lib/api";
import type { MockProfile } from "../lib/types";
import { useAppStore } from "../store/useAppStore";

export function ImportPage() {
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ id: number; name?: string } | null>(null);
  const [mockProfiles, setMockProfiles] = useState<MockProfile[]>([]);
  const [generating, setGenerating] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const setView = useAppStore((s) => s.setView);
  const setSelected = useAppStore((s) => s.setSelectedActivity);

  useEffect(() => {
    api.listMockProfiles().then((d) => setMockProfiles(d.profiles));
  }, []);

  const onUpload = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".fit")) {
      alert("V0.1.0 仅支持 .fit 文件");
      return;
    }
    setUploading(true);
    setProgress(0);
    setUploadResult(null);
    try {
      const r = await api.uploadActivity(file, setProgress);
      setUploadResult({ id: r.id });
    } catch (e) {
      alert("上传失败:" + (e as Error).message);
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
      // 自动跳转详情页
      setSelected(r.id);
      setView("activity-detail");
    } catch (e) {
      alert("生成失败:" + (e as Error).message);
    } finally {
      setGenerating(null);
    }
  };

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">
      <div>
        <h1 className="text-2xl font-semibold text-text-primary">导入训练</h1>
        <p className="text-sm text-text-muted mt-1">
          上传 FIT 文件,或者用模拟数据先体验。
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
            accept=".fit"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onUpload(f);
            }}
          />
          {uploading ? (
            <>
              <div className="text-sm text-text-primary mb-2">上传中... {progress}%</div>
              <div className="w-64 mx-auto h-1.5 bg-bg-input rounded-full overflow-hidden">
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
                onClick={() => {
                  setSelected(uploadResult.id);
                  setView("activity-detail");
                }}
                className="ml-auto btn-ghost text-accent-primary"
              >
                查看分析 →
              </button>
            </div>
            <div className="text-xs text-amber-400 flex items-center gap-1.5 pt-1 border-t border-border">
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
