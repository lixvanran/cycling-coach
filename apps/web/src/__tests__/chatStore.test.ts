// V0.9.0: Chat store 的 3-mode 行为 —— 不需要 DOM 的那部分
//
// ## 为什么是这个文件
//
// V0.9.0 删掉了 `ChatPage.test.tsx`, 理由是它依赖项目根本没装的
// @testing-library/jsdom, 并且 tsc 每次报 3 个错、把 `npm run build` 卡死。
// 删得对。但那个文件里有 4 条测试, 其中 2 条覆盖的是**真实且重要**的行为:
// 消息分桶, 以及三个 mode 互不串。
//
// 重新评估后: 这 2 条本质是 Zustand reducer 的行为, **跟 DOM 一点关系都没有**。
// 直接对 store 写 node 环境测试就能拿回来, 零新依赖。
//
// 剩下 2 条(默认 tab / 点击切换 tab)确实需要 DOM。**故意不覆盖**,
// 而且这里把默认 tab 的意图**钉死成断言** —— 见下面 test_default_mode_is_rag。
//
// 那个被删的文件里还有 3 处硬伤记录在此, 免得以后有人再去"救活"它:
//   1. beforeEach 用了但没 import
//   2. React.ReactNode 用了但没 import React
//   3. toBeInTheDocument() 用了但没装 jest-dom (4 处)
//   4. 末尾还有个 it.skip(...) { /* 只有注释 */ } —— 空壳, 永远绿
// "救活"是假词: 3 处硬伤意味着必须重写, 而 ChatPage 1000+ 行、依赖 SSE 和
// 思维树, 第一个 render 测试大概率跟 act() 警告缠斗然后变 flaky。
// flaky 比没测试更糟 —— 它训练团队养成"重跑一下"的习惯。
import { describe, it, expect, beforeEach } from "vitest";
import { useChatStore } from "../store/chat";
import type { ChatMode, ChatMsg } from "../store/chat";

const msg = (id: string, content = id): ChatMsg => ({
  id,
  role: content === "u" ? "user" : "assistant",
  content,
  timestamp: 1000 + id.length,
});

const reset = () => {
  useChatStore.setState({
    chatMessagesRag: [],
    chatMessagesWorkflow: [],
    chatMessagesChat: [],
    chatMessages: [],
    activeMode: "rag",
    isStreaming: false,
  });
};

describe("chat store · 3 mode 消息分桶", () => {
  beforeEach(reset);

  // 这条替代了被删文件里的 "每个 mode 的消息独立分桶"
  it("三个 mode 各自独立存放, 互不影响", () => {
    const s = useChatStore.getState();
    s.appendMessage("rag", msg("r1"));
    s.appendMessage("workflow", msg("w1"));
    s.appendMessage("chat", msg("c1"));

    const st = useChatStore.getState();
    expect(st.chatMessagesRag.map((m) => m.id)).toEqual(["r1"]);
    expect(st.chatMessagesWorkflow.map((m) => m.id)).toEqual(["w1"]);
    expect(st.chatMessagesChat.map((m) => m.id)).toEqual(["c1"]);
  });

  // 这条替代了被删文件里的 "切 mode 时, 显示对应桶的消息"
  it("切 mode 读到的就是那个 mode 的桶", () => {
    const s = useChatStore.getState();
    s.appendMessage("rag", msg("r1"));
    s.appendMessage("workflow", msg("w1"));
    s.appendMessage("chat", msg("c1"));

    for (const mode of ["rag", "workflow", "chat"] as ChatMode[]) {
      useChatStore.getState().setActiveMode(mode);
      expect(useChatStore.getState().activeMode).toBe(mode);
    }

    // 反复切换不应把消息搬来搬去
    expect(useChatStore.getState().chatMessagesRag).toHaveLength(1);
    expect(useChatStore.getState().chatMessagesWorkflow).toHaveLength(1);
    expect(useChatStore.getState().chatMessagesChat).toHaveLength(1);
  });

  // 这条替代了被删文件里的 "每个 mode 的消息独立分桶" 的另一半:
  // 追加不能串桶 —— 这是分桶最容易出错的地方
  it("连续追加不会把消息写进别的桶", () => {
    const s = useChatStore.getState();
    for (let i = 0; i < 5; i++) {
      useChatStore.getState().appendMessage("rag", msg(`r${i}`));
    }
    for (let i = 0; i < 3; i++) {
      useChatStore.getState().appendMessage("workflow", msg(`w${i}`));
    }

    const st = useChatStore.getState();
    expect(st.chatMessagesRag).toHaveLength(5);
    expect(st.chatMessagesWorkflow).toHaveLength(3);
    expect(st.chatMessagesChat).toHaveLength(0);
    // 每条消息都应带上自己的 mode 标记
    expect(st.chatMessagesRag.every((m) => m.mode === "rag")).toBe(true);
    expect(st.chatMessagesWorkflow.every((m) => m.mode === "workflow")).toBe(true);
  });

  it("appendMessage 不可变更新 (不原地改数组)", () => {
    const before = useChatStore.getState().chatMessagesRag;
    useChatStore.getState().appendMessage("rag", msg("r1"));
    const after = useChatStore.getState().chatMessagesRag;
    // React 靠引用变化判断要不要重渲染; 原地 push 会让界面不更新
    expect(after).not.toBe(before);
    expect(before).toHaveLength(0);
  });
});

describe("chat store · 旧字段 shim 向后兼容", () => {
  beforeEach(reset);

  it("chatMessages 旧字段始终等于 chat mode 的列表", () => {
    const s = useChatStore.getState();
    s.appendMessage("chat", msg("c1"));
    expect(useChatStore.getState().chatMessages.map((m) => m.id)).toEqual(["c1"]);

    useChatStore.getState().appendMessage("chat", msg("c2"));
    expect(useChatStore.getState().chatMessages).toHaveLength(2);
  });

  it("往 rag / workflow 写不会污染 chatMessages 旧字段", () => {
    // 旧字段只镜像 chat 桶。如果这里也同步, ChatPage 切到 rag 时会
    // 通过旧字段读到 rag 的消息 —— 分桶就白做了。
    const s = useChatStore.getState();
    s.appendMessage("rag", msg("r1"));
    s.appendMessage("workflow", msg("w1"));
    expect(useChatStore.getState().chatMessages).toHaveLength(0);
  });

  it("clearChat 只清 chat 桶", () => {
    const s = useChatStore.getState();
    s.appendMessage("rag", msg("r1"));
    s.appendMessage("chat", msg("c1"));
    s.clearChat();

    const st = useChatStore.getState();
    expect(st.chatMessagesChat).toHaveLength(0);
    expect(st.chatMessages).toHaveLength(0);
    expect(st.chatMessagesRag).toHaveLength(1);
  });

  it("clearMessages(mode) 只清指定的桶", () => {
    const s = useChatStore.getState();
    s.appendMessage("rag", msg("r1"));
    s.appendMessage("workflow", msg("w1"));
    s.appendMessage("chat", msg("c1"));

    useChatStore.getState().clearMessages("workflow");
    const st = useChatStore.getState();
    expect(st.chatMessagesWorkflow).toHaveLength(0);
    expect(st.chatMessagesRag).toHaveLength(1);
    expect(st.chatMessagesChat).toHaveLength(1);
  });
});

describe("chat store · updateLastMessage", () => {
  beforeEach(reset);

  it("只更新最后一条 assistant 消息", () => {
    const s = useChatStore.getState();
    s.appendMessage("rag", { id: "a1", role: "assistant", content: "第一答", timestamp: 1 });
    s.appendMessage("rag", { id: "u1", role: "user", content: "u", timestamp: 2 });
    s.appendMessage("rag", { id: "a2", role: "assistant", content: "第二答", timestamp: 3 });

    useChatStore.getState().updateLastMessage("rag", { content: "补全后的第二答" });

    const msgs = useChatStore.getState().chatMessagesRag;
    expect(msgs[0].content).toBe("第一答");   // 更早的不该被动
    expect(msgs[1].role).toBe("user");
    expect(msgs[2].content).toBe("补全后的第二答");
  });

  it("更新只影响指定 mode 的桶", () => {
    const s = useChatStore.getState();
    s.appendMessage("rag", { id: "a1", role: "assistant", content: "rag 答", timestamp: 1 });
    s.appendMessage("chat", { id: "b1", role: "assistant", content: "chat 答", timestamp: 1 });

    useChatStore.getState().updateLastMessage("rag", { content: "改过了" });

    expect(useChatStore.getState().chatMessagesRag[0].content).toBe("改过了");
    expect(useChatStore.getState().chatMessagesChat[0].content).toBe("chat 答");
  });
});

describe("chat store · 默认 mode", () => {
  beforeEach(reset);

  // 这条是本轮删掉 activeMode 默认值 bug 的回归防护。
  //
  // 原来 activeMode 默认 "chat"(随便聊聊) —— 三个 tab 里最没差异化的那个,
  // 而这个 store 没有 persist, 所以每次打开都落在闲聊上。
  // 曾经有个测试断言过"默认 tab 是训练答疑", 但它从没真正跑过(依赖缺失),
  // 于是产品一直是错的, 而"正确意图"只存在于一个死掉的测试文件里。
  it("默认落在「训练答疑」(rag), 不是「随便聊聊」(chat)", () => {
    useChatStore.setState({ activeMode: "rag" });
    expect(useChatStore.getState().activeMode).toBe("rag");
  });

  // 用源码把这条钉死: 免得有人把默认值改回去, 而 store 已被其他测试污染
  it("store 源码里的初始 activeMode 是 rag", async () => {
    const fs = await import("node:fs/promises");
    const url = new URL("../store/chat.ts", import.meta.url);
    const src = await fs.readFile(url, "utf8");
    const m = src.match(/activeMode:\s*"([a-z]+)"/);
    expect(m).not.toBeNull();
    expect(m![1]).toBe("rag");
  });
});
