<script setup lang="ts">
import { ref } from "vue";
import { api } from "../api";

const channelId = ref("");
const sendText = ref("");
const mockText = ref("");
const busy = ref(false);
const error = ref("");
const history: { kind: "send" | "mock" | "error"; text: string }[] = [];

async function doSend() {
  if (!channelId.value.trim() || !sendText.value.trim()) return;
  busy.value = true;
  error.value = "";
  try {
    const res = await api.chatSend({
      channel_id: channelId.value.trim(),
      channel_type: "private",
      text: sendText.value.trim(),
    });
    history.push({ kind: "send", text: `→ ${channelId.value.trim()} (private): ${sendText.value.trim()}  [id=${res.message_id}]` });
    sendText.value = "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
    history.push({ kind: "error", text: `✗ 发送失败: ${error.value}` });
  } finally {
    busy.value = false;
  }
}

async function doMock() {
  if (!mockText.value.trim()) return;
  busy.value = true;
  error.value = "";
  try {
    await api.chatMock(mockText.value.trim());
    history.push({ kind: "mock", text: `✎ 注入消息: ${mockText.value.trim()}` });
    mockText.value = "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    busy.value = false;
  }
}

const kindCls: Record<string, string> = {
  send: "text-slate-300",
  mock: "text-emerald-300",
  error: "text-red-300",
};
const kindTag: Record<string, string> = {
  send: "出",
  mock: "注",
  error: "错",
};
</script>

<template>
  <div class="grid gap-6 lg:grid-cols-2">
    <section class="card p-5">
      <h2 class="text-sm font-semibold text-slate-300">出向发送（私聊 adapter.send）</h2>
      <div class="mt-4 space-y-4">
        <div>
          <label class="mb-1.5 block text-xs text-slate-500">目标 user_id（微信用户）</label>
          <input
            v-model="channelId"
            class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
            placeholder="如 wxu-123"
          />
        </div>
        <div>
          <label class="mb-1.5 block text-xs text-slate-500">文本</label>
          <input
            v-model="sendText"
            class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
            placeholder="要发送的内容"
            @keyup.enter="doSend"
          />
        </div>
        <button
          class="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-indigo-500/25 transition hover:opacity-90 disabled:opacity-50"
          :disabled="busy || !channelId.trim() || !sendText.trim()"
          @click="doSend"
        >发送</button>
      </div>
    </section>

    <section class="card p-5">
      <h2 class="text-sm font-semibold text-slate-300">入向模拟（注入 MESSAGE_RECEIVE）</h2>
      <div class="mt-4 space-y-4">
        <input
          v-model="mockText"
          class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20"
          placeholder="模拟一条平台消息文本（走完整逻辑链）"
          @keyup.enter="doMock"
        />
        <button
          class="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-emerald-500/25 transition hover:opacity-90 disabled:opacity-50"
          :disabled="busy || !mockText.trim()"
          @click="doMock"
        >注入</button>
      </div>
    </section>

    <section class="card p-5 lg:col-span-2">
      <h2 class="text-sm font-semibold text-slate-300">动作记录</h2>
      <p v-if="error" class="mt-2 text-xs text-red-300">{{ error }}</p>
      <ul class="terminal mt-3 max-h-64 space-y-1.5 overflow-auto text-xs">
        <li v-for="(item, i) in history" :key="i" class="flex items-start gap-2">
          <span class="mt-px shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[10px]" :class="kindCls[item.kind]">{{ kindTag[item.kind] }}</span>
          <span :class="kindCls[item.kind]">{{ item.text }}</span>
        </li>
        <li v-if="!history.length" class="text-slate-500">暂无动作，尝试发送或注入一条消息。</li>
      </ul>
    </section>
  </div>
</template>
