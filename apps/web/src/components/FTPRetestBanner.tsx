// FTP 复测提醒 — V0.7.1 补遗漏
// 借鉴 Gabbett 2016 训练负荷悖论 + 训练区校准
//
// 触发条件 (来自 /api/ftp/recommend):
// - days_since >= 84 (12 周, Gabbett 上限)
// - 14d IF avg > 0.85 (强度突破)
// - 4-8 周但 14d IF 持续高

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Gauge, ArrowRight, X } from "lucide-react";

interface FTPRecommend {
  days_since: number | null;
  last_ftp_w: number;
  last_method: string;
  last_test_date: string | null;
  avg_if_last_14d: number;
  should_test: boolean;
  reason: string;
  recommended_method: string;
  priority: "high" | "medium" | "low";
}

const PRIORITY_STYLE: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  high: { bg: "bg-rose-50", border: "border-rose-200", text: "text-rose-700", icon: "text-rose-500" },
  medium: { bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-700", icon: "text-amber-500" },
  low: { bg: "bg-slate-50", border: "border-slate-200", text: "text-slate-600", icon: "text-slate-400" },
};

const METHOD_LABEL: Record<string, string> = {
  coggan_20min: "Coggan 20min",
  carmichael_8min: "Carmichael 8min×2",
  cp_3param: "CP 3-param",
  ramp_test: "Ramp Test",
  auto: "Auto (自动选最优)",
};

export function FTPRetestBanner() {
  const navigate = useNavigate();
  const [data, setData] = useState<FTPRecommend | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    fetch("/api/ftp/recommend")
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(() => {});
  }, []);

  if (!data || dismissed) return null;
  if (!data.should_test) return null;

  const style = PRIORITY_STYLE[data.priority] || PRIORITY_STYLE.low;

  return (
    <div className={`rounded-2xl border ${style.border} ${style.bg} p-4 mb-4 relative`}>
      <button
        onClick={() => setDismissed(true)}
        className="absolute top-2 right-2 p-1 rounded hover:bg-white/50"
        aria-label="关闭"
      >
        <X className="w-3.5 h-3.5 text-slate-400" />
      </button>

      <div className="flex items-start gap-3 pr-6">
        <Gauge className={`w-5 h-5 mt-0.5 ${style.icon}`} />
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <div className={`text-sm font-semibold ${style.text}`}>
              {data.priority === "high" ? "建议尽快复测 FTP" : "考虑安排 FTP 测试"}
            </div>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${style.text} bg-white/60 font-medium`}>
              优先级 {data.priority}
            </span>
          </div>
          <div className="text-xs text-slate-600 mt-1 leading-relaxed">{data.reason}</div>
          {data.last_test_date && (
            <div className="text-[10px] text-slate-500 mt-1.5">
              上次测试: {data.last_ftp_w}W ({data.last_method}) · {data.days_since} 天前 · 近期 IF {data.avg_if_last_14d.toFixed(2)}
            </div>
          )}
          <div className="flex items-center gap-2 mt-2">
            <button
              onClick={() => navigate("/data/ftp-test")}
              className="px-3 py-1.5 text-xs font-medium rounded bg-accent-primary text-white hover:opacity-90 transition flex items-center gap-1.5"
            >
              去测试
              <ArrowRight className="w-3 h-3" />
            </button>
            <span className="text-[10px] text-slate-500">
              推荐协议: {METHOD_LABEL[data.recommended_method] || data.recommended_method}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
