// 知识库浏览 (V0.5 全新 UX)
// 左 1/3: 分类树 + 搜索 + 热门标签
// 右 2/3: 推荐卡片 / 搜索结果 / 文档详情 (含面包屑)
// 关键改进 (V0.5):
//   1. 树支持全选/全折叠, 字母排序, 选中高亮, doc_count 彩色 badge
//   2. 面包屑路径快速跳转
//   3. 顶部热门标签: FTP/甜区/VO2/恢复 一键跳转搜索
//   4. 主页: 随机推荐 3 篇文章卡片
//   5. 搜索: 高亮匹配关键词
import { useEffect, useMemo, useState, useCallback } from "react";
import {
  Search, Library, ChevronRight, ChevronDown, FileText, Image as ImageIcon, X,
  ArrowLeft, Eye, Hash, Sparkles, Star, BookOpen, TrendingUp,
  PanelLeftClose, PanelLeftOpen, Home, ArrowRight, Tag, Filter, Layers,
} from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
import type { KbCategory, KbDocument, KbDocumentSummary, KbStats, KbSearchResult } from "../lib/types";

// 热门标签 (4 个常用概念)
const HOT_TAGS = [
  { key: "FTP", label: "FTP 测试", color: "bg-accent-danger", emoji: "⚡" },
  { key: "甜区", label: "甜区训练", color: "bg-accent-warning", emoji: "🍯" },
  { key: "VO2max", label: "VO2max", color: "bg-accent-primary", emoji: "🔥" },
  { key: "恢复", label: "训练恢复", color: "bg-accent-cyan", emoji: "💧" },
  { key: "节奏", label: "节奏训练", color: "bg-accent-warning", emoji: "⛰️" },
  { key: "功率", label: "功率训练", color: "bg-accent-success", emoji: "📊" },
];

// ===== 简易 markdown 渲染 =====
function renderMarkdown(md: string): { __html: string } {
  let html = md;
  html = html.replace(/!\[([^\]]*)\]\(attachments\/([^)]+)\)/g,
    (_, alt, fname) => `<img class="kb-img" loading="lazy" decoding="async" data-filename="${fname}" alt="${alt}" src="/api/kb/attachments/by-name/${encodeURIComponent(fname)}" />`);
  html = html.replace(/```([\s\S]*?)```/g, (_, code) => `<pre class="kb-pre"><code>${escapeHtml(code)}</code></pre>`);
  html = html.replace(/`([^`]+)`/g, (_, code) => `<code class="kb-code">${escapeHtml(code)}</code>`);
  html = html.replace(/^# (.+)$/gm, '<h1 class="kb-h1">$1</h1>');
  html = html.replace(/^## (.+)$/gm, '<h2 class="kb-h2">$1</h2>');
  html = html.replace(/^### (.+)$/gm, '<h3 class="kb-h3">$1</h3>');
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a class="kb-link" data-path="$2" href="#">$1</a>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  html = html.replace(/^- (.+)$/gm, '<li class="kb-li">$1</li>');
  html = html.replace(/(<li class="kb-li">[\s\S]+?<\/li>)(?!\n<li)/g, '<ul class="kb-ul">$1</ul>');
  html = html.split(/\n\n+/).map((para) => {
    if (para.match(/^<[a-zA-Z]/)) return para;
    return `<p class="kb-p">${para}</p>`;
  }).join("\n");
  return { __html: html };
}
function escapeHtml(s: string) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// 高亮匹配词 - 返回 HTML 字符串 (供 dangerouslySetInnerHTML)
// 高亮所有匹配 (V0.8.2 U-20: 之前只高亮第一个, 用户看不到全文命中密度)
function highlight(text: string, kw: string): string {
  if (!kw) return escapeHtml(text);
  const lower = text.toLowerCase();
  const kwl = kw.toLowerCase();
  let result = "";
  let i = 0;
  while (i < text.length) {
    const idx = lower.indexOf(kwl, i);
    if (idx < 0) {
      result += escapeHtml(text.slice(i));
      break;
    }
    result += escapeHtml(text.slice(i, idx));
    result += `<mark class="bg-yellow-200 text-text-primary font-semibold rounded px-0.5">${escapeHtml(text.slice(idx, idx + kw.length))}</mark>`;
    i = idx + kw.length;
  }
  return result;
}

// 计算关键词命中数
function countMatches(text: string, kw: string): number {
  if (!kw) return 0;
  const lower = text.toLowerCase();
  const kwl = kw.toLowerCase();
  let count = 0;
  let i = 0;
  while (i < text.length) {
    const idx = lower.indexOf(kwl, i);
    if (idx < 0) break;
    count++;
    i = idx + kw.length;
  }
  return count;
}

export function KnowledgeBasePage() {
  const [categories, setCategories] = useState<KbCategory[]>([]);
  const [stats, setStats] = useState<KbStats | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<KbDocument | null>(null);
  const [docs, setDocs] = useState<KbDocumentSummary[]>([]);
  const [searchQ, setSearchQ] = useState("");
  const [searchRes, setSearchRes] = useState<KbSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  // 推荐文章
  const [recommended, setRecommended] = useState<KbDocumentSummary[]>([]);
  // 加载状态
  const [loadingDocs, setLoadingDocs] = useState(false);

  // 初始加载
  useEffect(() => {
    (async () => {
      try {
        const [c, s] = await Promise.all([api.kbCategories(), api.kbStats()]);
        setCategories(c.categories || []);
        setStats(s);
        // 默认全展开
        setExpanded(new Set((c.categories || []).map((x) => x.path)));
        // 推荐: 取 3 个随机文档 (KB 已自动过滤 decoration)
        const recs = await api.kbDocuments({ limit: 60, offset: 0 });
        setRecommended((recs.documents || []).sort(() => Math.random() - 0.5).slice(0, 3));
      } catch (e) { /* ignore */ }
    })();
  }, []);

  // 搜索 (debounce)
  useEffect(() => {
    if (!searchQ.trim()) { setSearchRes([]); return; }
    setSearching(true);
    const t = setTimeout(async () => {
      try {
        const r = await api.kbSearch(searchQ, 30);
        setSearchRes(r.results || []);
      } finally { setSearching(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [searchQ]);

  // 选 path → 加载文档
  useEffect(() => {
    if (!selectedPath) { setDocs([]); return; }
    setLoadingDocs(true);
    (async () => {
      try {
        const r = await api.kbDocuments({ path: selectedPath, limit: 100, offset: 0 });
        setDocs(r.documents || []);
      } finally { setLoadingDocs(false); }
    })();
  }, [selectedPath]);

  // 全选/全折叠
  const allPaths = useMemo(() => {
    const s = new Set<string>();
    categories.forEach((c) => s.add(c.path));
    return s;
  }, [categories]);
  const expandAll = () => setExpanded(new Set(allPaths));
  const collapseAll = () => setExpanded(new Set());

  // 树: 按 path 排序
  const sortedCategories = useMemo(() => [...categories].sort((a, b) => a.path.localeCompare(b.path, "zh-Hans")), [categories]);

  // 面包屑
  const breadcrumbs = useMemo(() => {
    if (!selectedPath) return [];
    return selectedPath.split("/").filter(Boolean);
  }, [selectedPath]);

  return (
    <div className="h-full flex flex-col bg-bg-base">
      {/* 顶部固定栏 */}
      <div className="flex-shrink-0 px-6 pt-5 pb-3 bg-white border-b border-border sticky top-0 z-20">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
              <div className="w-9 h-9 rounded flex items-center justify-center bg-accent-primary text-white">
                <Library className="w-5 h-5" />
              </div>
              训练百科
              <span className="text-[10px] text-text-muted font-normal ml-1 px-1.5 py-0.5 rounded bg-bg-subtle">潘震(公路车教练) 知识库</span>
            </h1>
            <p className="text-xs text-text-muted mt-1.5">功率训练 · 运动生理 · 营养恢复 · 装备调校 · 赛事策略</p>
          </div>
          {stats && (
            <div className="flex items-center gap-3 text-xs">
              <div className="text-right">
                <div className="text-[10px] text-text-muted uppercase">文档</div>
                <div className="text-base font-bold text-accent tabular-nums">{stats.documents}</div>
              </div>
              <div className="text-right">
                <div className="text-[10px] text-text-muted uppercase">分块</div>
                <div className="text-base font-bold text-accent tabular-nums">{stats.chunks}</div>
              </div>
              <div className="text-right">
                <div className="text-[10px] text-text-muted uppercase">附件</div>
                <div className="text-base font-bold text-accent tabular-nums">{stats.attachments}</div>
              </div>
            </div>
          )}
        </div>
        {/* 搜索框 + 热门标签 */}
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-[200px] max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
            <input
              value={searchQ}
              onChange={(e) => setSearchQ(e.target.value)}
              placeholder="搜索训练百科…如 'FTP 怎么测' / '甜区' / 'VO2'"
              className="w-full pl-9 pr-9 py-2 bg-white border-2 border-border rounded text-sm focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
            />
            {searchQ && (
              <button onClick={() => setSearchQ("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary">
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
          <button
            onClick={() => setShowSidebar((v) => !v)}
            className="p-2 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-subtle"
            title={showSidebar ? "隐藏分类" : "显示分类"}
          >
            {showSidebar ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeftOpen className="w-4 h-4" />}
          </button>
        </div>
        <div className="mt-2 flex items-center gap-1.5 flex-wrap">
          <span className="text-[10px] text-text-muted flex items-center gap-1 flex-shrink-0">
            <Tag className="w-3 h-3" />热门标签:
          </span>
          {HOT_TAGS.map((t) => (
            <button
              key={t.key}
              onClick={() => setSearchQ(t.key)}
              className={clsx("px-2.5 py-1 rounded-full text-[11px] font-semibold text-white bg-accent-primary transition-all flex items-center gap-1", t.color)}
            >
              <span>{t.emoji}</span>{t.label}
            </button>
          ))}
        </div>
      </div>

      {/* 主体 */}
      <div className="flex-1 flex min-h-0">
        {/* 左侧分类树 */}
        {showSidebar && (
          <CategorySidebar
            categories={sortedCategories}
            expanded={expanded}
            setExpanded={setExpanded}
            selectedPath={selectedPath}
            setSelectedPath={setSelectedPath}
            expandAll={expandAll}
            collapseAll={collapseAll}
            totalDocs={stats?.documents || 0}
          />
        )}

        {/* 右侧内容 */}
        <div className="flex-1 overflow-auto">
          {/* 搜索结果模式 */}
          {searchQ.trim() && (
            <SearchResultsView
              q={searchQ}
              results={searchRes}
              searching={searching}
              onOpenDoc={(d) => {
                api.kbDocument(d.id).then(setSelectedDoc).catch(() => {});
                setSearchQ("");
              }}
            />
          )}

          {/* 文档详情模式 */}
          {!searchQ.trim() && selectedDoc && (
            <DocDetailView
              doc={selectedDoc}
              onBack={() => setSelectedDoc(null)}
              onLinkClick={(path) => {
                // 站内链接: 找对应文档
                const fname = path.split("/").pop() || "";
                const clean = fname.replace(/\.md$/, "");
                if (clean) {
                  api.kbByPath(`${clean}.md`).then((d) => {
                    if (d) setSelectedDoc(d);
                  }).catch(() => {});
                }
              }}
            />
          )}

          {/* 目录模式 (默认) */}
          {!searchQ.trim() && !selectedDoc && (
            <DirectoryView
              breadcrumbs={breadcrumbs}
              selectedPath={selectedPath}
              docs={docs}
              loading={loadingDocs}
              onOpenDoc={(d) => {
                api.kbDocument(d.id).then(setSelectedDoc).catch(() => {});
              }}
              onJumpCrumb={(i) => {
                if (i < 0) { setSelectedPath(null); return; }
                const path = breadcrumbs.slice(0, i + 1).join("/");
                setSelectedPath(path);
              }}
              onPickCategory={(p) => setSelectedPath(p)}
              categories={sortedCategories}
              recommended={recommended}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// =============== 左侧分类树 ===============
function CategorySidebar(props: {
  categories: KbCategory[]; expanded: Set<string>; setExpanded: (s: Set<string>) => void;
  selectedPath: string | null; setSelectedPath: (p: string | null) => void;
  expandAll: () => void; collapseAll: () => void; totalDocs: number;
}) {
  // 按顶级分组 → 子节点
  const tree = useMemo(() => {
    const map = new Map<string, KbCategory[]>();
    for (const c of props.categories) {
      const parts = c.path.split("/");
      const top = parts[0];
      if (!map.has(top)) map.set(top, []);
      map.get(top)!.push(c);
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b, "zh-Hans"));
  }, [props.categories]);

  return (
    <div className="w-72 flex-shrink-0 border-r border-border bg-bg-subtle/40 flex flex-col">
      <div className="p-3 border-b border-border flex items-center justify-between flex-shrink-0">
        <div className="text-xs font-semibold flex items-center gap-1.5">
          <Layers className="w-3.5 h-3.5 text-accent" />
          分类
          <span className="text-[10px] text-text-muted font-normal ml-1">{props.categories.length}</span>
        </div>
        <div className="flex items-center gap-0.5">
          <button onClick={props.expandAll} className="text-[10px] px-1.5 py-0.5 rounded text-text-muted hover:text-accent hover:bg-accent/10" title="全部展开">⊞</button>
          <button onClick={props.collapseAll} className="text-[10px] px-1.5 py-0.5 rounded text-text-muted hover:text-accent hover:bg-accent/10" title="全部折叠">⊟</button>
        </div>
      </div>
      <div className="flex-1 overflow-auto p-2">
        {/* 全部 (根) */}
        <button
          onClick={() => props.setSelectedPath(null)}
          className={clsx("w-full flex items-center gap-1.5 px-2 py-1.5 rounded text-xs font-semibold transition",
            props.selectedPath === null ? "bg-accent text-white shadow-md" : "hover:bg-bg-subtle text-text-primary"
          )}
        >
          <Home className="w-3.5 h-3.5" />
          <span className="flex-1 text-left">全部</span>
          <span className={clsx("text-[10px] px-1.5 py-0.5 rounded font-bold tabular-nums", props.selectedPath === null ? "bg-white/20 text-white" : "bg-bg-subtle text-text-muted")}>
            {props.totalDocs}
          </span>
        </button>

        {tree.map(([top, items]) => {
          const topCat = items.find((i) => i.path === top);
          const topExpanded = props.expanded.has(top);
          const topCount = items.reduce((s, i) => s + (i.doc_count || 0), 0);
          const isTopSelected = props.selectedPath === top;
          return (
            <div key={top} className="mt-1">
              <div className={clsx("flex items-center gap-1 rounded transition group", isTopSelected ? "bg-accent/15 ring-1 ring-accent/30" : "hover:bg-bg-subtle")}>
                <button
                  onClick={() => props.setExpanded(topExpanded ? new Set([...props.expanded].filter((x) => x !== top)) : new Set([...props.expanded, top]))}
                  className="p-1 text-text-muted hover:text-text-primary"
                >
                  {topExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                </button>
                <button
                  onClick={() => props.setSelectedPath(top)}
                  className="flex-1 text-left py-1.5 text-xs font-semibold truncate"
                >
                  {topCat?.name || top}
                </button>
                <span className={clsx("text-[10px] px-1.5 py-0.5 rounded font-bold mr-1 tabular-nums",
                  isTopSelected ? "bg-accent text-white" :
                  topCount > 50 ? "bg-status-info text-accent-primary" :
                  topCount > 20 ? "bg-status-warning text-accent-warning" :
                  topCount > 5 ? "bg-status-info text-accent-primary" :
                  "bg-bg-subtle text-text-muted"
                )}>{topCount}</span>
              </div>
              {topExpanded && (
                <div className="ml-3 mt-0.5 border-l border-border/40 pl-1">
                  {items.filter((i) => i.path !== top).map((c) => {
                    const isSelected = props.selectedPath === c.path;
                    return (
                      <button
                        key={c.path}
                        onClick={() => props.setSelectedPath(c.path)}
                        className={clsx("w-full flex items-center gap-1.5 px-2 py-1 rounded text-[11px] transition text-left",
                          isSelected ? "bg-accent/15 text-accent font-semibold" : "text-text-secondary hover:bg-bg-subtle hover:text-text-primary"
                        )}
                        title={c.path}
                      >
                        <FileText className="w-3 h-3 flex-shrink-0 opacity-60" />
                        <span className="truncate flex-1">{c.name || c.path}</span>
                        {c.doc_count !== undefined && (
                          <span className={clsx("text-[9px] px-1 rounded tabular-nums", isSelected ? "bg-accent/30 text-accent" : "text-text-muted")}>
                            {c.doc_count}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// =============== 目录视图 ===============
function DirectoryView(props: {
  breadcrumbs: string[]; selectedPath: string | null; docs: KbDocumentSummary[];
  loading: boolean;
  onOpenDoc: (d: KbDocumentSummary) => void;
  onJumpCrumb: (i: number) => void;
  onPickCategory: (p: string) => void;
  categories: KbCategory[];
  recommended: KbDocumentSummary[];
}) {
  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* 面包屑 */}
      <div className="flex items-center gap-1 text-xs text-text-muted mb-4 flex-wrap">
        <button onClick={() => props.onJumpCrumb(-1)} className="flex items-center gap-1 hover:text-accent">
          <Home className="w-3 h-3" />全部
        </button>
        {props.breadcrumbs.map((crumb, i) => (
          <span key={i} className="flex items-center gap-1">
            <ChevronRight className="w-3 h-3 opacity-50" />
            <button
              onClick={() => props.onJumpCrumb(i)}
              className={clsx("hover:text-accent", i === props.breadcrumbs.length - 1 ? "text-text-primary font-semibold" : "")}
            >
              {crumb}
            </button>
          </span>
        ))}
      </div>

      {/* 推荐区 (仅在根目录显示) */}
      {!props.selectedPath && props.recommended.length > 0 && (
        <div className="mb-6">
          <h2 className="text-sm font-bold flex items-center gap-1.5 mb-3 text-text-primary">
            <Sparkles className="w-4 h-4 text-accent-warning" />
            编辑推荐
            <span className="text-[10px] text-text-muted font-normal ml-1">每次随机</span>
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {props.recommended.map((d) => (
              <DocCard key={d.id} doc={d} onOpen={() => props.onOpenDoc(d)} featured />
            ))}
          </div>
        </div>
      )}

      {/* 顶部分类速览 (仅根目录) */}
      {!props.selectedPath && (
        <div className="mb-6">
          <h2 className="text-sm font-bold flex items-center gap-1.5 mb-3 text-text-primary">
            <TrendingUp className="w-4 h-4 text-accent" />
            浏览分类
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {props.categories.filter((c) => c.path.split("/").length === 1).map((c) => (
              <button
                key={c.path}
                onClick={() => props.onPickCategory(c.path)}
                className="group p-3 bg-white rounded border-2 border-border/50 hover:border-accent/50 hover:shadow-md transition text-left"
              >
                <div className="text-sm font-bold text-text-primary group-hover:text-accent truncate">{c.name}</div>
                <div className="text-[10px] text-text-muted mt-0.5 flex items-center gap-1">
                  <FileText className="w-3 h-3" />
                  <span>{c.doc_count || 0} 篇</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 文档列表 (只在选了具体分类时显示) */}
      {props.selectedPath && (
        <div>
          <h2 className="text-sm font-bold flex items-center gap-1.5 mb-3 text-text-primary">
            <FileText className="w-4 h-4 text-accent" />
            {props.breadcrumbs[props.breadcrumbs.length - 1] || "文档"}
            <span className="text-[10px] text-text-muted font-normal ml-1">{props.docs.length} 篇</span>
          </h2>
          {props.loading ? (
            <div className="text-text-muted text-sm text-center py-8">加载中…</div>
          ) : props.docs.length === 0 ? (
            <div className="text-text-muted text-sm text-center py-12 bg-white rounded border border-dashed border-border">
              <FileText className="w-10 h-10 mx-auto mb-2 opacity-30" />
              这个目录下还没有内容
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              {props.docs.map((d) => (
                <DocCard key={d.id} doc={d} onOpen={() => props.onOpenDoc(d)} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// =============== 文档卡片 ===============
function DocCard({ doc, onOpen, featured }: { doc: KbDocumentSummary; onOpen: () => void; featured?: boolean }) {
  return (
    <button
      onClick={onOpen}
      className={clsx(
        "group p-3 bg-white rounded border-2 text-left transition-all",
        featured
          ? "border-border hover:border-border hover:shadow-sm bg-status-warning"
          : "border-border/40 hover:border-accent/40 hover:shadow-md"
      )}
    >
      <div className="flex items-start gap-2">
        {featured && <Star className="w-3.5 h-3.5 text-accent-warning flex-shrink-0 mt-0.5" />}
        <div className="flex-1 min-w-0">
          <div className={clsx("font-semibold truncate", featured ? "text-base text-text-primary group-hover:text-accent-warning" : "text-sm text-text-primary group-hover:text-accent")}>
            {doc.title}
          </div>
          <div className="text-[11px] text-text-muted mt-1 line-clamp-2 leading-relaxed">
            {doc.path}
          </div>
          <div className="flex items-center gap-2 mt-1.5 text-[10px] text-text-muted">
            <span className="flex items-center gap-0.5"><Hash className="w-2.5 h-2.5" />{doc.path.split("/").slice(0, 2).join("/")}</span>
            {doc.attachment_count > 0 && <span className="flex items-center gap-0.5"><ImageIcon className="w-2.5 h-2.5" />{doc.attachment_count}</span>}
            <span className="ml-auto opacity-0 group-hover:opacity-100 text-accent flex items-center gap-0.5">阅读<ArrowRight className="w-2.5 h-2.5" /></span>
          </div>
        </div>
      </div>
    </button>
  );
}

// =============== 搜索结果 ===============
function SearchResultsView({ q, results, searching, onOpenDoc }: {
  q: string; results: KbSearchResult[]; searching: boolean; onOpenDoc: (d: KbDocumentSummary) => void;
}) {
  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h2 className="text-base font-bold mb-3 flex items-center gap-2">
        <Search className="w-4 h-4 text-accent" />
        搜索 "<span className="text-accent">{q}</span>"
        {searching ? <span className="text-text-muted text-xs">搜索中…</span> :
          <span className="text-text-muted text-xs">{results.length} 条</span>
        }
      </h2>
      {results.length === 0 && !searching ? (
        <div className="text-text-muted text-sm text-center py-12 bg-white rounded border border-dashed border-border">
          <Search className="w-10 h-10 mx-auto mb-2 opacity-30" />
          没有找到相关内容
          <div className="text-[11px] mt-2">试试热门标签: {HOT_TAGS.map((t) => t.label).join(", ")}</div>
        </div>
      ) : (
        <div className="space-y-2">
          {results.map((r, i) => (
            <button
              key={`${r.chunk_id}-${i}`}
              onClick={() => onOpenDoc({
                id: r.document_id,
                title: r.document_title || "(无标题)",
                path: r.document_path,
                excerpt: r.snippet,
                depth: 0, parent_path: null, chunk_count: 0, attachment_count: 0,
              } as KbDocumentSummary)}
              className="w-full text-left p-3 bg-white rounded border border-border/50 hover:border-accent hover:shadow-md transition"
            >
              <div className="text-sm font-semibold text-text-primary">{r.document_title || "(无标题)"}</div>
              <div className="text-[11px] text-text-muted mt-0.5 flex items-center gap-1.5">
                <span>{r.document_path}</span>
                {q && countMatches(r.document_title || "", q) > 0 && (
                  <span className="text-[9px] bg-yellow-100 text-yellow-800 px-1 rounded font-bold">
                    标题命中
                  </span>
                )}
              </div>
              {r.snippet && (
                <div
                  className="text-[11px] text-text-secondary mt-1 line-clamp-3"
                  dangerouslySetInnerHTML={{ __html: highlight(r.snippet, q) }}
                />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// =============== 文档详情 ===============
function DocDetailView({ doc, onBack, onLinkClick }: {
  doc: KbDocument; onBack: () => void; onLinkClick: (path: string) => void;
}) {
  const html = useMemo(() => renderMarkdown(doc.content_md || ""), [doc.content_md]);
  useEffect(() => {
    // 拦截链接点击
    const handler = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (t.tagName === "A" && t.classList.contains("kb-link")) {
        e.preventDefault();
        const path = t.getAttribute("data-path") || "";
        onLinkClick(path);
      }
    };
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, [onLinkClick]);

  return (
    <div className="h-full flex flex-col bg-white">
      <div className="flex-shrink-0 px-6 py-3 border-b border-border bg-white sticky top-0 z-10">
        <button onClick={onBack} className="text-xs text-accent hover:text-accent/80 flex items-center gap-1 mb-1.5 font-semibold">
          <ArrowLeft className="w-3 h-3" />返回目录
        </button>
        <h1 className="text-2xl font-bold text-text-primary">{doc.title}</h1>
        <div className="flex items-center gap-3 mt-1.5 text-xs text-text-muted">
          <span className="flex items-center gap-1"><Hash className="w-3 h-3" />{doc.path}</span>
          {doc.attachment_count > 0 && <span className="flex items-center gap-1"><ImageIcon className="w-3 h-3" />{doc.attachment_count} 张图</span>}
          <span>{doc.content_md ? Math.ceil(doc.content_md.length / 600) : 0} 分钟阅读</span>
        </div>
      </div>
      <div className="flex-1 overflow-auto px-6 py-4">
        <article
          className="kb-article max-w-3xl mx-auto"
          dangerouslySetInnerHTML={html}
        />
      </div>
    </div>
  );
}
