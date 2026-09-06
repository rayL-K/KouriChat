<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { api, type LogRow } from "../api";

const rows = ref<LogRow[]>([]);
const level = ref("DEBUG");
const error = ref("");
const listEl = ref<HTMLElement | null>(null);
let timer: number | undefined;

async function refresh() {
  try {
    rows.value = (await api.logs(500, level.value)).logs;
    error.value = "";
    await nextTick();
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

function clear() {
  rows.value = [];
}

watch(level, refresh);
onMounted(() => {
  refresh();
  timer = window.setInterval(refresh, 2000);
});
onUnmounted(() => {
  if (timer !== undefined) window.clearInterval(timer);
});

const levelColor: Record<string, string> = {
  DEBUG: "text-slate-500",
  INFO: "text-sky-300",
  WARNING: "text-amber-300",
  ERROR: "text-red-300",
};
const levelBadge: Record<string, string> = {
  DEBUG: "bg-slate-800 text-slate-400",
  INFO: "bg-sky-500/15 text-sky-300",
  WARNING: "bg-amber-500/15 text-amber-300",
  ERROR: "bg-red-500/15 text-red-300",
};
</script>

<template>
  <section class="card p-5">
    <div class="flex flex-wrap items-center gap-3">
      <h2 class="text-sm font-semibold text-slate-300">运行日志（loguru 环形缓冲）</h2>
      <div class="ml-auto flex items-center gap-2">
        <select
          v-model="level"
          class="rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs outline-none focus:border-indigo-500"
        >
          <option value="DEBUG">DEBUG</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
        </select>
        <button
          class="rounded-lg bg-slate-800 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700"
          @click="clear"
        >清空显示</button>
      </div>
    </div>
    <p v-if="error" class="mt-2 text-xs text-red-300">{{ error }}</p>

    <div
      ref="listEl"
      class="terminal mt-3 h-[26rem] overflow-auto rounded-xl border border-slate-800 bg-slate-950/80 p-3 text-xs leading-relaxed"
    >
      <p v-if="!rows.length" class="text-slate-600">暂无日志（webui 启动后开始捕获）</p>
      <div
        v-for="(row, i) in rows"
        :key="i"
        class="flex gap-2 border-b border-slate-900/60 py-1"
      >
        <span class="shrink-0 text-slate-600">{{ row.time }}</span>
        <span class="shrink-0 rounded px-1.5 py-0.5 text-[10px] leading-4" :class="levelBadge[row.level] ?? 'bg-slate-800 text-slate-400'">{{ row.level }}</span>
        <span :class="levelColor[row.level] ?? 'text-slate-300'">{{ row.line }}</span>
      </div>
    </div>
  </section>
</template>
