#!/usr/bin/env node
/**
 * 前端产物资源路径检查 — Node 版 — V0.9.1
 *
 * 为什么要写 Node 版: `ci.yml` 的 frontend job 只装了 Node, 没有 Python。
 * 放一个 `python tools/...` 进去会直接失败 —— **新增 CI 步骤必须先确认
 * runner 上有对应的运行时**, 否则是自己给自己弄红。
 *
 * 检查的 bug: `vite.config.ts` 的 `base: "./"` 会让 index.html 里写
 * `./assets/index-xxx.js`; 浏览器在 `/plan/calendar` 下解析成
 * `/plan/assets/index-xxx.js` -> 404 -> SPA fallback 返回 index.html
 * (MIME `text/html`) -> 浏览器拒绝加载 JS 模块 -> **该页面完全不执行**,
 * 空白骨架且不报错。
 *
 * 根路径 `/` 恰好正常, 所以首页好好的、一进子页面就空了, 躲过好几轮 review。
 *
 * 和 Python 版 `tools/check_frontend_asset_paths.py` 等价, 保留两份是因为:
 *   - CI 的 frontend job 只有 Node
 *   - 本地/交付前检查走 Python 版(和 tools/ 下其他检查一致)
 * 改动时**两份都要改**, 且用对方的输出对拍一次。
 *
 * 用法: node tools/check_frontend_asset_paths.mjs
 */
import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const STATIC_DIR = resolve(ROOT, "cycling_coach/static");
const INDEX = resolve(STATIC_DIR, "index.html");

if (!existsSync(INDEX)) {
  console.error(`❌ 没找到 ${INDEX}`);
  console.error("   前端还没构建。跑: cd apps/web && npx vite build");
  process.exit(1);
}

const html = readFileSync(INDEX, "utf8");
const refs = [...html.matchAll(/(?:src|href)="([^"]*assets\/[^"]*)"/g)].map((m) => m[1]);

if (refs.length === 0) {
  console.error("❌ index.html 里没找到任何 assets 引用 —— 产物可能是空的");
  process.exit(1);
}

console.log(`检查 ${refs.length} 个资源引用 (static/index.html)`);

const problems = [];

for (const ref of refs) {
  if (ref.startsWith("./") || !ref.startsWith("/")) {
    problems.push(
      `${ref}\n` +
        `    → 相对路径。浏览器在 /plan/calendar 下会解析成 /plan/${ref.replace(/^\.\//, "")}\n` +
        `    → 404 → SPA fallback 返回 index.html(MIME text/html)\n` +
        `    → 该页面的 JS 完全不执行, 渲染成空白骨架\n` +
        `    修法: vite.config.ts 的 base 改成 "/"`,
    );
  }
  const target = resolve(STATIC_DIR, ref.replace(/^\//, ""));
  if (!existsSync(target)) {
    problems.push(
      `${ref} → 引用了不存在的文件 ${target.split("/").pop()}\n` +
        `    → 部署后 404。要么重新构建, 要么产物没同步。`,
    );
  }
}

if (problems.length > 0) {
  for (const p of problems) console.error(`❌ ${p}\n`);
  console.error("❌ 前端资源路径有问题。");
  console.error("   这些页面在用户机器上会是**空白**的, 而且不报任何错。");
  process.exit(1);
}

console.log(`✅ 全部 ${refs.length} 个资源引用都是绝对路径, 且文件存在`);
[...new Set(refs)].sort().forEach((r) => console.log(`   ${r}`));