<script setup lang="ts">
import { onMounted, reactive, ref, watch } from "vue";
import { api, type SettingsFields } from "../api";

const fields = reactive<SettingsFields>({
  core: { log_level: "INFO" },
  openclaw: {
    gateway_url: "http://127.0.0.1:8765",
    access_token: "",
    data_dir: "./data",
    autologin: true,
    poll_interval: 2.0,
  },
  llm: { base_url: "https://api.openai.com/v1", api_key: "", model: "gpt-4o-mini", data_dir: "./data" },
  webui: { host: "127.0.0.1", port: 8080 },
  persona: { personas_dir: "./personas", enable: "" },
  echo: { enabled: true },
});

const loading = ref(true);
const status = ref<"idle" | "saving" | "saved" | "error">("idle");
const error = ref("");
let saveTimer: number | undefined;
let saving = false;
let ready = false;

async function load() {
  loading.value = true;
  try {
    const res = await api.settingsGet();
    Object.assign(fields, res.fields);
    ready = true; // 加载完成后才允许自动保存（避免打开即写文件）
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
    status.value = "error";
  } finally {
    loading.value = false;
  }
}

async function doSave() {
  if (saving) return;
  saving = true;
  status.value = "saving";
  error.value = "";
  try {
    await api.settingsSave(JSON.parse(JSON.stringify(fields)));
    status.value = "saved";
  } catch (err) {
    status.value = "error";
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    saving = false;
  }
}

// 输入变化 → 防抖 800ms 自动保存（即时保存）
watch(fields, () => {
  if (!ready) return;
  status.value = "idle";
  if (saveTimer !== undefined) window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(doSave, 800);
}, { deep: true });

// —— LLM 连通测试 ——
const testing = ref(false);
const testResult = ref<{ ok: boolean; text: string } | null>(null);

async function testLlm() {
  testing.value = true;
  testResult.value = null;
  try {
    const r = await api.llmTest(JSON.parse(JSON.stringify(fields.llm)));
    testResult.value = r.ok
      ? { ok: true, text: `✅ 连通正常（${r.model ?? ""}）：${r.reply ?? ""}` }
      : { ok: false, text: `❌ ${r.error ?? "未知错误"}` };
  } catch (err) {
    testResult.value = { ok: false, text: `❌ ${err instanceof Error ? err.message : String(err)}` };
  } finally {
    testing.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center gap-3">
      <h2 class="text-lg font-semibold text-slate-100">设置</h2>
      <span
        class="rounded-full px-2.5 py-1 text-xs font-medium"
        :class="{
          'bg-emerald-500/15 text-emerald-300': status === 'saved',
          'bg-amber-500/15 text-amber-300': status === 'saving',
          'bg-red-500/15 text-red-300': status === 'error',
          'bg-slate-800 text-slate-400': status === 'idle',
        }"
      >
        {{ status === "saving" ? "保存中…" : status === "saved" ? "已保存" : status === "error" ? "保存失败" : "修改即自动保存" }}
      </span>
      <span v-if="error" class="rounded-lg bg-red-500/15 px-2 py-1 text-xs text-red-300">{{ error }}</span>
    </div>

    <p v-if="loading" class="text-sm text-slate-400">加载中…</p>
    <template v-else>
      <!-- 核心 -->
      <section class="card p-5">
        <h3 class="mb-4 text-sm font-semibold text-slate-300">核心</h3>
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">日志级别</label>
            <select v-model="fields.core.log_level" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500">
              <option value="DEBUG">DEBUG</option><option value="INFO">INFO</option><option value="WARNING">WARNING</option><option value="ERROR">ERROR</option>
            </select>
          </div>
        </div>
      </section>

      <!-- OpenClaw 网关 -->
      <section class="card p-5">
        <h3 class="mb-4 text-sm font-semibold text-slate-300">OpenClaw 网关</h3>
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">网关地址</label>
            <input v-model="fields.openclaw.gateway_url" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" placeholder="http://127.0.0.1:8765" />
          </div>
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">Access Token</label>
            <input v-model="fields.openclaw.access_token" type="password" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" placeholder="网关 config.json 的 accessToken" />
          </div>
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">数据目录</label>
            <input v-model="fields.openclaw.data_dir" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
          </div>
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">轮询间隔（秒）</label>
            <input v-model.number="fields.openclaw.poll_interval" type="number" min="0.2" step="0.1" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
          </div>
          <div class="sm:col-span-2">
            <label class="flex items-center gap-2 text-sm text-slate-300">
              <input v-model="fields.openclaw.autologin" type="checkbox" class="h-4 w-4 rounded accent-indigo-500" />
              无本地账号时自动发起扫码登录
            </label>
          </div>
        </div>
      </section>

      <!-- LLM -->
      <section class="card p-5">
        <div class="mb-4 flex items-center justify-between">
          <h3 class="text-sm font-semibold text-slate-300">LLM（elixir / OpenAI 兼容）</h3>
          <button
            class="rounded-lg bg-slate-800 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700 disabled:opacity-50"
            :disabled="testing"
            @click="testLlm"
          >{{ testing ? "测试中…" : "测试连通" }}</button>
        </div>
        <p
          v-if="testResult"
          class="mb-3 rounded-lg px-3 py-2 text-xs"
          :class="testResult.ok ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'"
        >{{ testResult.text }}</p>
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">Base URL</label>
            <input v-model="fields.llm.base_url" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
          </div>
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">API Key</label>
            <input v-model="fields.llm.api_key" type="password" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" placeholder="sk-..." />
          </div>
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">模型</label>
            <input v-model="fields.llm.model" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
          </div>
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">数据目录</label>
            <input v-model="fields.llm.data_dir" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
          </div>
        </div>
      </section>

      <!-- echo 默认任务 -->
      <section class="card p-5">
        <h3 class="mb-4 text-sm font-semibold text-slate-300">默认任务</h3>
        <div class="grid gap-4 sm:grid-cols-2">
          <div class="sm:col-span-2">
            <label class="flex items-center gap-2 text-sm text-slate-300">
              <input v-model="fields.echo.enabled" type="checkbox" class="h-4 w-4 rounded accent-indigo-500" />
              echo 回显（收到 /echo 后原样回显下一条消息；开启时这两条消息不进命令/大模型）
            </label>
          </div>
        </div>
      </section>

      <!-- WebUI 人设 -->
      <section class="card p-5">
        <h3 class="mb-4 text-sm font-semibold text-slate-300">WebUI / 人设</h3>
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">WebUI 监听地址</label>
            <input v-model="fields.webui.host" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
          </div>
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">WebUI 端口</label>
            <input v-model.number="fields.webui.port" type="number" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
          </div>
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">人设目录</label>
            <input v-model="fields.persona.personas_dir" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
          </div>
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">启用人设</label>
            <input v-model="fields.persona.enable" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" placeholder="可留空取第一个" />
          </div>
        </div>
      </section>

      <p class="text-xs text-slate-500">更改会自动保存到 {{ "kourichat.toml" }}（TOML 校验后原子写入），部分设置需重启生效。</p>
    </template>
  </div>
</template>
