<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import * as d3 from "d3";
import { api, type Status } from "../api";

const props = defineProps<{ status: Status | null }>();

const personas = ref<{ count: number; active: string | null }>({ count: 0, active: null });
const firstRun = ref(false);
const donutEl = ref<HTMLElement | null>(null);
const sparkEl = ref<HTMLElement | null>(null);
let dashTimer: number | undefined;
let logTimer: number | undefined;

// —— 数字滚动（KPI 计数动画）——
const accountsNum = ref(0);
const onlineNum = ref(0);
const personasNum = ref(0);
function countUp(target: number, set: (n: number) => void, duration = 900) {
  const start = performance.now();
  const from = 0;
  function frame(now: number) {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    set(Math.round(from + (target - from) * eased));
    if (t < 1) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

async function refreshDashboard() {
  try {
    const d = await api.dashboard();
    personas.value = d.personas;
    firstRun.value = d.first_run;
    countUp(d.personas.count, (n) => { personasNum.value = n; });
  } catch (err) {
    console.warn("dashboard fetch failed", err);
  }
}

async function refreshSpark() {
  try {
    const { logs } = await api.logs(500, "DEBUG");
    drawSpark(logs.map((l: any) => new Date(l.time).getTime()));
  } catch {
    /* 图表留空 */
  }
}

function drawDonut() {
  if (!donutEl.value) return;
  const counts: Record<string, number> = { online: 0, invalid: 0, offline: 0 };
  for (const a of props.status?.accounts ?? []) counts[a.status] = (counts[a.status] ?? 0) + 1;
  const data = Object.entries(counts).map(([status, value]) => ({ status, value })).filter((d) => d.value > 0);
  const total = data.reduce((s, d) => s + d.value, 0);
  const el = donutEl.value as HTMLElement;
  el.innerHTML = "";
  if (!total) return;
  const colors: Record<string, string> = { online: "#34d399", invalid: "#fb7185", offline: "#94a3b8" };
  const W = 190, R = 74;
  const svg = d3.select(el).append("svg").attr("width", W).attr("height", W)
    .append("g").attr("transform", `translate(${W / 2},${W / 2})`);
  const arc = d3.arc<any>().innerRadius(R - 28).outerRadius(R);
  const pie = d3.pie<any>().value((d: any) => d.value).sort(null);
  svg.selectAll("path").data(pie(data)).enter().append("path")
    .attr("d", arc as any)
    .attr("fill", (d: any) => colors[d.data.status] ?? "#64748b")
    .attr("stroke", "#05060f").attr("stroke-width", "3")
    .style("filter", (d: any) => `drop-shadow(0 0 8px ${colors[d.data.status] ?? "#64748b"}55)`)
    .style("transition", "d .5s ease, fill .4s ease");
  const mid = svg.append("g");
  mid.append("text").attr("text-anchor", "middle").attr("dy", "0.35em")
    .attr("fill", "#e2e8f0").attr("font-size", "30").attr("font-weight", "700")
    .text(String(total));
  mid.append("text").attr("text-anchor", "middle").attr("dy", "24")
    .attr("fill", "#64748b").attr("font-size", "11").text("账号");
}

function drawSpark(times: number[]) {
  if (!sparkEl.value) return;
  const el = sparkEl.value as HTMLElement;
  el.innerHTML = "";
  if (!times.length) {
    el.innerHTML = '<p class="text-slate-600 text-xs">暂无日志数据</p>';
    return;
  }
  const W = 560, H = 160, pad = 20;
  const now = Date.now();
  const windowMs = 10 * 60 * 1000;
  const buckets = 6;
  const binSize = windowMs / buckets;
  const bins = Array.from({ length: buckets }, (_, i) => ({
    t0: now - windowMs + i * binSize,
    count: times.filter((t) => t >= now - windowMs + i * binSize && t < now - windowMs + (i + 1) * binSize).length,
  }));
  const max = Math.max(1, d3.max(bins, (b) => b.count) ?? 1);
  const x = d3.scaleBand<number>().domain(bins.map((b, i) => i)).range([pad, W - pad]).padding(0.28);
  const y = d3.scaleLinear().domain([0, max]).range([H - pad, pad]);
  const svg = d3.select(el).append("svg").attr("width", W).attr("height", H);
  // 网格线条（纹理）
  for (let i = 0; i <= 4; i++) {
    const yy = pad + ((H - 2 * pad) / 4) * i;
    svg.append("line").attr("x1", pad).attr("x2", W - pad).attr("y1", yy).attr("y2", yy)
      .attr("stroke", "rgba(99,102,241,0.12)").attr("stroke-dasharray", "3 5");
  }
  // 柱 + 顶部渐变
  svg.selectAll("rect").data(bins).enter().append("rect")
    .attr("x", (d: any, i: number) => x(i) as number)
    .attr("y", (d: any) => y(d.count))
    .attr("width", Math.max(4, x.bandwidth()))
    .attr("height", (d: any) => (H - pad) - y(d.count))
    .attr("rx", 4)
    .attr("fill", "url(#grad-bar)")
    .style("filter", "drop-shadow(0 0 6px rgba(129,140,248,0.4))");
  const defs = svg.append("defs");
  const grad = defs.append("linearGradient").attr("id", "grad-bar").attr("x1", "0").attr("y1", "1").attr("x2", "0").attr("y2", "0");
  grad.append("stop").attr("offset", "0%").attr("stop-color", "#6366f1");
  grad.append("stop").attr("offset", "100%").attr("stop-color", "#a78bfa");
  // 基线
  svg.append("line").attr("x1", pad).attr("x2", W - pad).attr("y1", H - pad).attr("y2", H - pad)
    .attr("stroke", "rgba(148,163,184,0.25)");
  svg.append("text").attr("x", W - pad).attr("y", 14).attr("text-anchor", "end")
    .attr("fill", "#64748b").attr("font-size", "11").text("近 10 分钟日志频率");
}

function statusSummary() {
  const a = props.status?.accounts ?? [];
  const online = a.filter((x) => x.status === "online").length;
  return { online, invalid: a.filter((x) => x.status === "invalid").length, offline: a.filter((x) => x.status === "offline").length };
}

watch(() => props.status, () => {
  drawDonut();
  const a = props.status?.accounts ?? [];
  countUp(a.length, (n) => { accountsNum.value = n; });
  countUp(a.filter((x) => x.status === "online").length, (n) => { onlineNum.value = n; });
}, { deep: true });

onMounted(() => {
  refreshDashboard();
  refreshSpark();
  dashTimer = window.setInterval(refreshDashboard, 5000);
  logTimer = window.setInterval(refreshSpark, 4000);
  drawDonut();
});
onUnmounted(() => {
  if (dashTimer !== undefined) window.clearInterval(dashTimer);
  if (logTimer !== undefined) window.clearInterval(logTimer);
});
</script>

<template>
  <div class="space-y-6">
    <!-- KPI -->
    <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <section class="card p-5">
        <p class="text-xs font-medium uppercase tracking-wide text-slate-500">网关连接</p>
        <p class="mt-2 flex items-center gap-2 text-2xl font-semibold">
          <span class="pulse-dot h-2.5 w-2.5 rounded-full" :class="status?.connected ? 'bg-emerald-400' : 'bg-red-400'"></span>
          {{ status?.connected ? "已连接" : "未连接" }}
        </p>
        <p v-if="status?.gateway_url" class="mt-2 truncate text-xs text-slate-400">{{ status.gateway_url }}</p>
      </section>

      <section class="card p-5">
        <p class="text-xs font-medium uppercase tracking-wide text-slate-500">已登录账号</p>
        <p class="mt-2 text-2xl font-semibold tabular-nums">{{ accountsNum }}<span class="ml-1 text-base font-normal text-slate-500">个</span></p>
        <p class="mt-2 text-xs text-slate-400">在线 <span class="tabular-nums">{{ onlineNum }}</span> · 失效 {{ statusSummary().invalid }}</p>
      </section>

      <section class="card p-5">
        <p class="text-xs font-medium uppercase tracking-wide text-slate-500">人设</p>
        <p class="mt-2 text-2xl font-semibold tabular-nums">{{ personasNum }}</p>
        <p class="mt-2 truncate text-xs text-slate-400">{{ personas.active ? `启用：${personas.active}` : "未启用" }}</p>
      </section>

      <section class="card p-5">
        <p class="text-xs font-medium uppercase tracking-wide text-slate-500">登录状态</p>
        <p class="mt-2 text-2xl font-semibold"
          :class="status?.login?.status === 'success' ? 'text-emerald-300' : status?.login?.status === 'failed' ? 'text-red-300' : 'text-amber-300'">
          {{ status?.login ? (status.login.status === "pending" ? "扫码中" : status.login.status === "success" ? "已登录" : "失败") : "未发起" }}
        </p>
        <p v-if="status?.login?.message" class="mt-2 truncate text-xs text-slate-400">{{ status.login.message }}</p>
      </section>
    </div>

    <!-- 图表 ×2 + 指引 -->
    <div class="grid gap-6 lg:grid-cols-3">
      <section class="card p-5">
        <h2 class="text-sm font-semibold text-slate-300">账号状态分布</h2>
        <div ref="donutEl" class="mt-4 flex items-center justify-center"></div>
        <div class="mt-2 flex items-center justify-center gap-4 text-xs">
          <span class="flex items-center gap-1.5 text-slate-400"><span class="h-2 w-2 rounded-full bg-emerald-400"></span>在线 {{ statusSummary().online }}</span>
          <span class="flex items-center gap-1.5 text-slate-400"><span class="h-2 w-2 rounded-full bg-red-400"></span>失效 {{ statusSummary().invalid }}</span>
          <span class="flex items-center gap-1.5 text-slate-400"><span class="h-2 w-2 rounded-full bg-slate-400"></span>离线 {{ statusSummary().offline }}</span>
        </div>
      </section>

      <section class="card p-5">
        <h2 class="text-sm font-semibold text-slate-300">活动频率</h2>
        <div ref="sparkEl" class="mt-4 overflow-x-auto"></div>
      </section>

      <section class="card p-5">
        <h2 class="text-sm font-semibold text-slate-300">快速指引</h2>
        <ul class="mt-3 space-y-2 text-sm text-slate-400">
          <li class="flex gap-2"><span class="text-indigo-400">›</span><span>「账号」页扫码登录 / 失效重登 / 登出。</span></li>
          <li class="flex gap-2"><span class="text-indigo-400">›</span><span>「聊天调试」页模拟入向或直发平台。</span></li>
          <li class="flex gap-2"><span class="text-indigo-400">›</span><span>「日志」页实时查看并过滤日志。</span></li>
          <li class="flex gap-2"><span class="text-indigo-400">›</span><span>「设置」页表单形式即时保存。</span></li>
        </ul>
        <p v-if="firstRun" class="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
          首次使用：先完成快速引导（API token / 登录账号），再接入正式网关。
        </p>
      </section>
    </div>

    <!-- 失效警示 -->
    <section v-if="status?.needs_relogin?.length" class="card border-amber-500/30 p-5">
      <div class="flex items-center gap-2">
        <span class="text-amber-300">⚠️</span>
        <h2 class="text-sm font-semibold text-amber-200">有账号登录失效，需要重新登录</h2>
      </div>
      <ul class="mt-3 flex flex-wrap gap-2">
        <li v-for="aid in status.needs_relogin" :key="aid" class="rounded-lg border border-amber-500/30 bg-slate-950/60 px-3 py-1.5 font-mono text-xs text-amber-200">{{ aid }}</li>
      </ul>
    </section>
  </div>
</template>
