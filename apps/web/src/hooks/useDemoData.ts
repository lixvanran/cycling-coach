// V0.9.0: "先看示例" 的共享逻辑
//
// ## 为什么抽出来
//
// 这个功能我先做在 DailyRecommendationCard 里, 但后来发现**新用户根本
// 看不到那张卡** —— Dashboard 在 `total_activities === 0` 时直接 early
// return 空状态, 卡片压根不渲染。
//
// 也就是说: 我做的"让新用户能看见产品好"的东西, **没接到新用户的主路径上**。
//
// 而"先看示例"恰恰是零数据用户最该看到的入口 —— 它让人在导入自己的
// 数据之前, 先看一眼这东西到底能算什么。
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";

export function useDemoData() {
  const navigate = useNavigate();
  const [loadingDemo, setLoadingDemo] = useState(false);
  const [demoMsg, setDemoMsg] = useState<string | null>(null);

  // ⚠️ 载入后**必须明确告诉用户这是示例**, 否则几十条活动混进他的库里,
  // 他会以为那些是自己骑的 —— 这正是我们这周一直在消灭的那类"骗人"。
  async function loadDemo() {
    setLoadingDemo(true);
    setDemoMsg(null);
    try {
      const r = await api.demoLoad(8, true);
      setDemoMsg(
        `已载入 ${r.n_activities} 次「${r.athlete_name}」的示例数据。` +
          `这是示例, 不是你的骑行记录 —— 导入你自己的 .fit 就会替换掉它。`
      );
      setTimeout(() => window.location.reload(), 1800);
    } catch (e) {
      setDemoMsg(`载入失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoadingDemo(false);
    }
  }

  return { navigate, loadDemo, loadingDemo, demoMsg };
}
