<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { api, type LogRow } from "../api";

const older = ref<LogRow[]>([]);      // 懒加载的更早日志（不随轮询变）
const latest = ref<LogRow[]>([]);     // 最新一页（轮询刷新）
const level = ref("DEBUG");
const error = ref("");
const listEl = ref<HTMLElement | null>(null);
const loadingOlder = ref(false);
const noMore = ref(false);
let timer: number | undefined;
let olderCount = 0;                   // 已加载的更早条数（= 后端 skip 偏移）
const PAGE = 300;

function atBottom(): boolean {
  const el = listEl.value;
  if (!el) return false;
  return el.scrollTop + el.clientHeight >= el.scrollHeight - 40;
}

async function refresh() {
  // 保持滚动位置：仅在刷新前位于底部时，刷新后跟随到底部
  const follow = atBottom();
  const prevTop = listEl.value?.scrollTop ?? 0;
  try {
    latest.value = (await api.logs(PAGE, level.value)).logs;
    error.value = "";
    await nextTick();
    if (follow) {
      const el = listEl.value;
      if (el) el.scrollTop = el.scrollHeight;
    } else if (listEl.value) {
      listEl.value.scrollTop = prevTop; // 不在底部 → 滚动位置原样保持
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function loadOlder() {
  if (loadingOlder.value || noMore.value) return;
  loadingOlder.value = true;
  error.value = "";
  const el = listEl.value;
  const prevHeight = el?.scrollHeight ?? 0;
  try {
    const rows = (await api.logs(PAGE, level.value, olderCount)).logs;
    if (!rows.length) {
      noMore.value = true;
      return;
    }
    older.value = [...rows, ...older.value];
    olderCount += rows.length;
    await nextTick();
    // 内容向前追加 → 补偿滚动位置，视觉上原地不动
    if (el) el.scrollTop += el.scrollHeight - prevHeight;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingOlder.value = false;
  }
}

function clear() {
  older.value = [];
  latest.value = [];
  olderCount = 0;
  noMore.value = false;
}

watch(level, () => {
  older.value = [];
  olderCount = 0;
  noMore.value = false;
  refresh();
});
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
    <p class="mt-1 text-xs text-slate-500">刷新不会改变滚动位置；滚动到顶可加载更早日志。</p>

    <div
      ref="listEl"
      class="terminal mt-3 h-[26rem] overflow-auto rounded-xl border border-slate-800 bg-slate-950/80 p-3 text-xs leading-relaxed"
    >
      <div class="sticky top-0 z-10 -mx-3 -mt-3 flex justify-center bg-slate-950/80 px-3 pb-1 pt-2 backdrop-blur">
        <button
          class="rounded-lg bg-slate-800 px-3 py-1 text-[11px] text-slate-300 hover:bg-slate-700 disabled:opacity-50"
          :disabled="loadingOlder || noMore"
          @click="loadOlder"
        >{{ noMore ? "没有更早的日志" : loadingOlder ? "加载中…" : "加载更早日志" }}</button>
      </div>

      <div
        v-for="(row, i) in [...older, ...latest]"
        :key="i"
        class="flex gap-2 border-b border-slate-900/60 py-1"
      >
        <span class="shrink-0 text-slate-600">{{ row.time }}</span>
        <span class="shrink-0 rounded px-1.5 py-0.5 text-[10px] leading-4" :class="levelBadge[row.level] ?? 'bg-slate-800 text-slate-400'">{{ row.level }}</span>
        <span :class="levelColor[row.level] ?? 'text-slate-300'">{{ row.line }}</span>
      </div>
      <p v-if="!older.length && !latest.length" class="text-slate-600">暂无日志（webui 启动后开始捕获）</p>
    </div>
  </section>
</template>
