#!/usr/bin/env node
/**
 * 浏览器全页面巡检 —— V0.9.1
 *
 * ## 为什么需要这个
 *
 * 2026-10-11 抓到过一个躲过多轮 review 的 P0:
 * `vite.config.ts` 的 `base: "./"` 让 index.html 写 `./assets/xxx.js`,
 * 浏览器在 `/plan/calendar` 下解析成 `/plan/assets/` -> 404 ->
 * SPA fallback 返回 text/html -> 浏览器拒绝加载 JS 模块 ->
 * **该页面一行 JS 都没执行**, 空白骨架, 且不报任何错。
 *
 * 它能藏住, 是因为 **根路径 `/` 恰好正常** —— 首页好好的,
 * 掩盖了"所有子页面全空"。人眼看首页没问题, 就这么放过了。
 *
 * 类型检查抓不到它, 单元测试抓不到它, 连"页面能打开"都抓不到。
 *
 * ## 所以记基线
 *
 * 每个页面的**可渲染文字量**是它的健康度。改动前后对比,
 * 数字掉了 = 那个页面退化了。
 *
 * 注意: 绝对值会随数据变化(有 demo 数据和没有差很多),
 * 所以本脚本:
 *   1. 用同一份种子数据
 *   2. 记录基线到文件
 *   3. 对比时允许小幅波动, 但**跌幅超过阈值就报红**
 *
 * ## 用法
 *
 *   node tools/browser_sweep.mjs record      # 记基线(改动后)
 *   node tools/browser_sweep.mjs compare     # 和基线对比
 *   node tools/browser_sweep.mjs show        # 只打印当前值
 *
 * 需要先起服务(默认 http://127.0.0.1:8799), 环境变量 BASE_URL 覆盖。
 */

import { writeFileSync, readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const BASELINE = resolve(ROOT, ".devtools/page_baseline.json");
const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:8799";

// 每个页面**必须**有实质内容。低于这个数就是"渲染坏了"。
// 这些是实测值的安全下限, 不是精确值。
const MIN_TEXT = {
  "/training": 800,
  "/training/activities": 800,
  "/training/trends": 800,
  "/plan/calendar": 300,
  "/plan/workouts": 2000,
  "/plan/phases": 600,
  "/data/import": 150,
  "/data/knowledge": 1000,
  "/data/trust": 500,
  "/data/ftp-test": 800,
  "/settings": 300,
  "/ai/chat": 200,
  "/ai/hrv": 400,
};

async function main() {
  const mode = process.argv[2] || "show";
  let chromium;
  try {
    ({ chromium } = await import(
      "/workspace/cycling-coach/.devtools/node_modules/playwright-core/index.mjs"
    ));
  } catch {
    console.error("❌ 找不到 playwright-core");
    process.exit(2);
  }

  const browser = await chromium.launch({
    executablePath:
      "/root/.cache/ms-playwright/chromium-1243/chrome-linux/chrome",
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  const results = {};
  const errors = [];

  for (const [path, minText] of Object.entries(MIN_TEXT)) {
    const errs = [];
    const onErr = (e) => errs.push(String(e.message).slice(0, 100));
    page.on("pageerror", onErr);

    try {
      await page.goto(BASE_URL + path, { waitUntil: "networkidle", timeout: 30000 });
      await page.waitForTimeout(1500);
      const text = await page.evaluate(() => document.body.innerText.length);
      results[path] = { text, ok: text >= minText && errs.length === 0, errs };
      if (errs.length) errors.push(`${path}: ${errs[0]}`);
    } catch (e) {
      results[path] = { text: 0, ok: false, errs: [e.message.slice(0, 80)] };
      errors.push(`${path}: 加载失败 ${e.message.slice(0, 60)}`);
    }
    page.removeListener("pageerror", onErr);
  }

  await browser.close();

  console.log(`\n页面巡检 @ ${BASE_URL}`);
  console.log("─".repeat(58));
  let bad = 0;
  for (const [path, r] of Object.entries(results)) {
    const minText = MIN_TEXT[path];
    const dropped =
      mode !== "compare" && existsSync(BASELINE)
        ? null
        : existsSync(BASELINE)
          ? results[path].text < (JSON.parse(readFileSync(BASELINE, "utf8"))[path]?.text ?? 0) * 0.6
          : false;
    const flag = !r.ok || dropped ? "❌" : "✅";
    if (!r.ok || dropped) bad++;
    console.log(`${flag} ${path.padEnd(22)} ${String(r.text).padStart(5)} (下限 ${minText})${dropped ? " ← 疑似退化" : ""}${r.errs[0] ? "  " + r.errs[0] : ""}`);
  }
  console.log("─".repeat(58));

  if (mode === "record") {
    writeFileSync(BASELINE, JSON.stringify(results, null, 2));
    console.log(`\n基线已写入 ${BASELINE.replace(ROOT + "/", "")}`);
  } else if (mode === "compare" && existsSync(BASELINE)) {
    const base = JSON.parse(readFileSync(BASELINE, "utf8"));
    for (const [p, r] of Object.entries(results)) {
      const b = base[p];
      if (b && r.text < b.text * 0.6) {
        console.log(`⚠️  ${p}: ${b.text} → ${r.text} (跌 ${Math.round((1 - r.text / b.text) * 100)}%)`);
      }
    }
  }

  if (errors.length) {
    console.log(`\n❌ ${errors.length} 个页面有问题:`);
    errors.forEach((e) => console.log(`   ${e}`));
  } else if (bad === 0) {
    console.log("\n✅ 全部页面正常");
  }

  process.exit(bad > 0 ? 1 : 0);
}

main().catch((e) => {
  console.error("巡检失败:", e.message);
  process.exit(2);
});