// 数据可信度 — V0.9.0
//
// ## 为什么要有这个页面
//
// 核心竞争点是「性能齐平 + 开源免费」。**"免费"本身就是最大的不信任理由**,
// 用户会想"免费的能靠谱吗"。
//
// 而我们这一周在 readiness / insights / race_prep / periodization 里清掉了
// 10 处"编造看起来合理的数据"的 bug —— **但用户一个都看不见**。
// 诚实如果不可见, 就等于不存在。
//
// 所以这个页面把那些内部约定摊开:
//   - 每个指标依据哪篇公开文献(可点进去核对)
//   - 你当前缺哪几维、为什么缺、怎么补
//   - 这个 App 在数据不足时会做什么、**不会**做什么
//
// 它不是营销页, 是**可核对的说明书**。
import { useEffect, useState } from "react";
import { ShieldCheck, ExternalLink, AlertCircle, CheckCircle2 } from "lucide-react";
import { api } from "../lib/api";
import type { TrustSelfCheck, TrustMetric } from "../lib/types";
import clsx from "clsx";

// 文献出处, 方便用户自己去核对原始论文
const LINKS: Record<string, string> = {
  "Plews et al. 2013": "https://pubmed.ncbi.nlm.nih.gov/23663347/",
  "Gabbett 2016": "https://bjsm.bmj.com/content/50/5/273",
  "Banister impulse-response model": "https://pubmed.ncbi.nlm.nih.gov/9699132/",
  "Joe Friel": "https://www.trainingpeaks.com/blog/",
};

function sourceUrl(src: string): string | null {
  for (const [k, v] of Object.entries(LINKS)) {
    if (src.startsWith(k)) return v;
  }
  return null;
}

export function TrustPage() {
  const [check, setCheck] = useState<TrustSelfCheck | null>(null);
  const [metrics, setMetrics] = useState<TrustMetric[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.trustSelfCheck(), api.trustMetrics()])
      .then(([c, m]) => {
        setCheck(c);
        setMetrics(m.metrics);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  if (err) {
    return (
      <div className="panel p-4 text-sm text-text-secondary">
        <AlertCircle className="w-4 h-4 inline mr-1" />
        读取失败: {err}
      </div>
    );
  }
  if (!check) {
    return <div className="panel p-4 text-sm text-text-muted">正在检查…</div>;
  }

  return (
    <div className="space-y-4">
      <div className="panel p-4">
        <div className="flex items-start gap-3">
          <ShieldCheck className="w-5 h-5 text-accent-success mt-0.5 flex-shrink-0" />
          <div className="flex-1">
            <h1 className="text-base font-semibold text-text-primary">
              你的数据现在能算出什么
            </h1>
            <p className="text-xs text-text-muted mt-1">
              v{check.version} · 车手 {check.athlete.name}
              {check.athlete.ftp ? ` · FTP ${check.athlete.ftp}W` : ""}
            </p>
            <div className="mt-2 text-sm">
              当前可用{" "}
              <span
                className={clsx(
                  "font-mono font-bold",
                  check.n_available === check.n_total
                    ? "text-accent-success"
                    : "text-accent-warning"
                )}
              >
                {check.n_available}/{check.n_total}
              </span>{" "}
              个维度
            </div>
          </div>
        </div>
      </div>

      {/* 维度状态 */}
      <div className="panel p-4">
        <h2 className="text-sm font-semibold text-text-primary mb-3">维度状态</h2>
        <div className="space-y-2">
          {check.dimensions.map((d) => (
            <div
              key={d.key}
              className="flex items-start gap-2 text-xs border-b border-border pb-2 last:border-0"
            >
              {d.available ? (
                <CheckCircle2 className="w-3.5 h-3.5 text-accent-success mt-0.5 flex-shrink-0" />
              ) : (
                <AlertCircle className="w-3.5 h-3.5 text-text-muted mt-0.5 flex-shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-2">
                  <span
                    className={clsx(
                      "font-medium",
                      d.available ? "text-text-primary" : "text-text-muted"
                    )}
                  >
                    {d.name}
                  </span>
                  <span className="text-[10px] text-text-muted">权重 {d.weight}</span>
                </div>
                <div className="text-text-muted mt-0.5">{d.why}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 算法出处 —— 开源的意义: 任何人都能核对 */}
      <div className="panel p-4">
        <h2 className="text-sm font-semibold text-text-primary mb-1">
          算法依据 (可核对)
        </h2>
        <p className="text-[11px] text-text-muted mb-3">
          这些指标不是我们发明的, 都是公开发表的训练学标准。
          源码在 GitHub 上, 你可以自己核对每一行怎么算的。
        </p>
        <div className="space-y-3">
          {metrics.map((m) => {
            const url = sourceUrl(m.source ?? "");
            return (
              <div key={m.key} className="text-xs">
                <div className="flex items-baseline gap-2">
                  <span className="font-medium text-text-primary">{m.name}</span>
                  {url && (
                    <a
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-0.5 text-[10px] text-accent-primary hover:underline"
                    >
                      原文 <ExternalLink className="w-2.5 h-2.5" />
                    </a>
                  )}
                </div>
                <div className="text-text-secondary mt-0.5">{m.source}</div>
                {m.note && (
                  <div className="text-text-muted mt-0.5">{m.note}</div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 我们的承诺 */}
      <div className="panel p-4">
        <h2 className="text-sm font-semibold text-text-primary mb-3">
          数据不足时, 这个 App 会怎么做
        </h2>
        <ul className="space-y-2">
          {check.policies.map((p, i) => (
            <li key={i} className="text-xs text-text-secondary flex gap-2">
              <span className="text-accent-success flex-shrink-0">·</span>
              <span>{p}</span>
            </li>
          ))}
        </ul>
        <div className="mt-3 pt-3 border-t border-border text-[11px] text-text-muted">
          为什么强调这个? 因为一个永远给你 82 分"状态极佳"的教练, 哪怕界面再漂亮,
          你也不能真的照着它骑车。
        </div>
      </div>
    </div>
  );
}

export default TrustPage;
