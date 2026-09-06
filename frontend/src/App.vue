<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { api, type Status } from "./api";
import Overview from "./views/Overview.vue";
import Accounts from "./views/Accounts.vue";
import ChatDebug from "./views/ChatDebug.vue";
import Logs from "./views/Logs.vue";
import ConfigView from "./views/Config.vue";
import Onboarding from "./views/Onboarding.vue";

const nav = [
  { key: "overview", label: "总览", icon: "M3 13h8V3H3v10zm10 8h8V11h-8v10zM3 21h8v-6H3v6zm10-18v6h8V3h-8z" },
  { key: "accounts", label: "账号", icon: "M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5s-3 1.34-3 3 1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z" },
  { key: "chat", label: "聊天调试", icon: "M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z" },
  { key: "logs", label: "日志", icon: "M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6a7 7 0 1 1 7 7 6.9 6.9 0 0 1-4.9-2L6.52 18.5A9 9 0 1 0 13 3zm-1 5v5l4.25 2.52.77-1.28-3.52-2.09V8H12z" },
  { key: "config", label: "设置", icon: "M19.14 12.94a7 7 0 0 0 .05-.94 7 7 0 0 0-.05-.94l2.03-1.58a.5.5 0 0 0 .12-.64l-1.92-3.32a.5.5 0 0 0-.61-.22l-2.39.96a7 7 0 0 0-1.62-.94l-.36-2.54a.5.5 0 0 0-.5-.42h-3.84a.5.5 0 0 0-.5.42l-.36 2.54c-.59.24-1.13.56-1.62.94l-2.39-.96a.5.5 0 0 0-.61.22L2.65 8.78a.5.5 0 0 0 .12.64l2.03 1.58a7 7 0 0 0 0 1.88L2.77 14.46a.5.5 0 0 0-.12.64l1.92 3.32c.13.23.42.31.61.22l2.39-.96c.49.38 1.03.7 1.62.94l.36 2.54c.04.24.25.42.5.42h3.84c.25 0 .46-.18.5-.42l.36-2.54a7 7 0 0 0 1.62-.94l2.39.96c.19.09.48.01.61-.22l1.92-3.32a.5.5 0 0 0-.12-.64l-2.03-1.58zM12 15.5A3.5 3.5 0 1 1 12 8.5a3.5 3.5 0 0 1 0 7z" },
] as const;
type NavKey = (typeof nav)[number]["key"];

const active = ref<NavKey>("overview");
const status = ref<Status | null>(null);
const statusError = ref("");
const mode = ref<"onboarding" | "console">("console");
let timer: number | undefined;

async function refresh() {
  try {
    status.value = await api.status();
    statusError.value = "";
  } catch (err) {
    statusError.value = err instanceof Error ? err.message : String(err);
  }
}

function accountOnlineCount(): number {
  return status.value?.accounts.filter((a) => a.status === "online").length ?? 0;
}

onMounted(async () => {
  // 首次使用：config 与模板一致 → 进入引导页
  try {
    const s = await api.setupStatus();
    if (s.first_run) mode.value = "onboarding";
  } catch {
    /* 忽略，按控制台模式 */
  }
  if (mode.value === "console") {
    refresh();
    timer = window.setInterval(refresh, 3000);
  }
});
onUnmounted(() => {
  if (timer !== undefined) window.clearInterval(timer);
});

function started() {
  mode.value = "console";
  refresh();
  if (timer === undefined) timer = window.setInterval(refresh, 3000);
}

function backToOnboarding() {
  mode.value = "onboarding";
}
</script>

<template>
  <!-- 首次使用引导 -->
  <Onboarding v-if="mode === 'onboarding'" @done="started" />

  <div v-else class="bg-grid flex min-h-screen">
    <!-- 侧边导航 -->
    <aside
      class="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col border-r border-slate-800/60 bg-slate-950/70 backdrop-blur-md md:flex"
    >
      <div class="flex items-center gap-2.5 px-5 py-5">
        <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-500 text-sm font-bold text-white">K</div>
        <div>
          <p class="text-sm font-semibold leading-tight text-slate-100">KouriChat</p>
          <p class="text-[11px] leading-tight text-slate-500">控制台</p>
        </div>
      </div>

      <nav class="mt-2 flex-1 space-y-1 px-3">
        <button
          v-for="n in nav"
          :key="n.key"
          class="group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition"
          :class="active === n.key
            ? 'bg-indigo-500/15 text-indigo-200'
            : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'"
          @click="active = n.key"
        >
          <svg viewBox="0 0 24 24" class="h-[18px] w-[18px]" fill="currentColor">
            <path :d="n.icon" />
          </svg>
          <span>{{ n.label }}</span>
        </button>
      </nav>

      <div class="border-t border-slate-800 px-5 py-4 text-xs text-slate-500">
        <p class="flex items-center gap-1.5">
          <span class="h-1.5 w-1.5 rounded-full" :class="status?.connected ? 'bg-emerald-400' : 'bg-red-400'"></span>
          {{ status?.connected ? "已连接网关" : "未连接网关" }}
        </p>
        <p class="mt-1 break-all">{{ status?.gateway_url }}</p>
        <button class="mt-3 text-slate-500 underline-offset-2 hover:text-slate-300 hover:underline" @click="backToOnboarding">重新走快速引导</button>
      </div>
    </aside>

      <!-- 主区域 -->
      <div class="flex min-h-screen flex-1 flex-col md:pl-60">
      <!-- 顶栏 -->
      <header class="sticky top-0 z-10 flex items-center gap-4 border-b border-slate-800/60 bg-slate-950/70 px-5 py-3.5 backdrop-blur-md">
        <div class="flex items-center gap-2 md:hidden">
          <div class="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-indigo-500 to-violet-500 text-xs font-bold text-white">K</div>
          <span class="text-sm font-semibold">控制台</span>
        </div>

        <h1 class="hidden text-lg font-semibold text-slate-100 md:block">
          {{ nav.find((n) => n.key === active)?.label }}
        </h1>

        <div class="ml-auto flex items-center gap-2">
          <span
            v-if="status && status.accounts.length"
            class="rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs text-slate-300"
          >
            {{ accountOnlineCount() }}/{{ status.accounts.length }} 在线
          </span>
          <span
            class="rounded-full px-2.5 py-1 text-xs font-medium"
            :class="status?.connected
              ? 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
              : 'border border-red-500/30 bg-red-500/10 text-red-300'"
          >
            <span class="mr-1 inline-block h-1.5 w-1.5 rounded-full align-middle" :class="status?.connected ? 'bg-emerald-400' : 'bg-red-400'"></span>
            {{ status?.connected ? "已连接" : "未连接" }}
          </span>
          <span v-if="statusError" class="hidden text-xs text-amber-300 sm:inline">{{ statusError }}</span>
        </div>
      </header>

      <!-- 移动端横向导航 -->
      <nav class="flex gap-1.5 overflow-x-auto border-b border-slate-800 bg-slate-950/60 px-3 py-2 md:hidden">
        <button
          v-for="n in nav"
          :key="n.key"
          class="rounded-lg px-3 py-1.5 text-xs whitespace-nowrap"
          :class="active === n.key ? 'bg-indigo-500 text-white' : 'bg-slate-800 text-slate-300'"
          @click="active = n.key"
        >
          {{ n.label }}
        </button>
      </nav>

      <main class="mx-auto w-full max-w-6xl flex-1 px-5 py-6">
        <Overview v-if="active === 'overview'" :status="status" />
        <Accounts v-else-if="active === 'accounts'" :status="status" @changed="refresh" />
        <ChatDebug v-else-if="active === 'chat'" />
        <Logs v-else-if="active === 'logs'" />
        <ConfigView v-else />
      </main>
    </div>
  </div>
</template>
