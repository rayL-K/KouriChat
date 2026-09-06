<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { api, type LoginState, type SettingsFields } from "../api";
import QrCode from "../components/QrCode.vue";

const emit = defineEmits<{ done: [] }>();

const step = ref(1);
const busy = ref(false);
const error = ref("");
const notice = ref("");
const loginState = ref<LoginState | null>(null);

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

onMounted(async () => {
  try {
    const res = await api.settingsGet();
    Object.assign(fields, res.fields);
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
});

async function saveSettings() {
  busy.value = true;
  error.value = "";
  try {
    await api.settingsSave(JSON.parse(JSON.stringify(fields)));
    notice.value = "设置已保存";
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    busy.value = false;
  }
}

async function next() {
  if (step.value === 1) {
    error.value = "";
    if (!fields.llm.api_key) {
      error.value = "请填写 LLM API Key（可稍后在设置页修改）";
      return;
    }
    await saveSettings();
    step.value = 2;
  } else if (step.value === 2) {
    await saveSettings();
    step.value = 3;
  }
}

async function startLogin() {
  busy.value = true;
  error.value = "";
  // 先保存网关配置：token/地址会热更新到运行中的适配器，再发起登录
  await saveSettings();
  if (error.value) {
    busy.value = false;
    return;
  }
  try {
    const st = await api.login();
    loginState.value = st;
    pollLogin();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    busy.value = false;
  }
}

async function pollLogin() {
  let tick = 0;
  const t = window.setInterval(async () => {
    tick += 1;
    try {
      const st = await api.status();
      loginState.value = st.login;
      if (st.login?.status === "success" || st.login?.status === "failed") {
        window.clearInterval(t);
      } else if (tick > 60) {
        window.clearInterval(t);
      }
    } catch {
      /* keep polling */
    }
  }, 1500);
}

async function finish() {
  await saveSettings();
  // 引导完成 → 运行时热重载 llm.factory（新 key/model 立即生效，无需重启进程）
  try {
    await api.llmReload();
  } catch {
    /* 热重载失败不阻断进入控制台 */
  }
  emit("done");
}

// —— LLM 连通测试（第 1 步）——
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
</script>

<template>
  <!-- 网格纹理铺满全屏，内容居中 -->
  <div class="bg-grid min-h-screen w-full">
    <div class="mx-auto max-w-2xl px-4 py-10">
      <div class="text-center">
        <div class="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 text-xl font-bold text-white">K</div>
        <h1 class="mt-4 text-2xl font-bold text-slate-100">欢迎使用 KouriChat</h1>
        <p class="mt-2 text-sm text-slate-400">首次使用，跟着三步完成最小配置：设置模型 API → 连接网关并登录 → 完成。</p>
      </div>

      <!-- 步进条 -->
      <div class="mt-8 flex items-center gap-2">
        <template v-for="i in 3" :key="i">
          <div class="flex-1 rounded-full h-1.5" :class="step >= i ? 'bg-indigo-500' : 'bg-slate-800'"></div>
        </template>
      </div>

    <section class="mt-8 card p-6">
      <!-- 步骤 1：LLM API -->
      <template v-if="step === 1">
        <h2 class="text-lg font-semibold text-slate-100">① 设置模型 API</h2>
        <p class="mt-1 text-xs text-slate-500">填写 LLM（OpenAI 兼容）的接入信息，用于角色扮演对话。</p>
        <div class="mt-5 space-y-4">
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">Base URL</label>
            <input v-model="fields.llm.base_url" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
          </div>
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">API Key <span class="text-red-400">*</span></label>
            <input v-model="fields.llm.api_key" type="password" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" placeholder="sk-..." />
          </div>
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">模型</label>
            <input v-model="fields.llm.model" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
          </div>
        </div>
        <div class="mt-4 flex items-center gap-3">
          <button
            class="rounded-lg bg-slate-800 px-4 py-2 text-xs text-slate-200 hover:bg-slate-700 disabled:opacity-50"
            :disabled="testing"
            @click="testLlm"
          >{{ testing ? "测试中…" : "测试连通" }}</button>
          <p
            v-if="testResult"
            class="rounded-lg px-3 py-2 text-xs"
            :class="testResult.ok ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'"
          >{{ testResult.text }}</p>
        </div>
      </template>

      <!-- 步骤 2：网关 + 登录 -->
      <template v-else-if="step === 2">
        <h2 class="text-lg font-semibold text-slate-100">② 连接网关并登录</h2>
        <p class="mt-1 text-xs text-slate-500">填写 weixin-gateway 可执行实例的地址，然后扫码登录微信。</p>
        <div class="mt-5 space-y-4">
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">网关地址</label>
            <input v-model="fields.openclaw.gateway_url" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
          </div>
          <div>
            <label class="mb-1.5 block text-xs text-slate-500">Access Token（网关 config.json 自动生成）</label>
            <input v-model="fields.openclaw.access_token" type="password" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-indigo-500" />
          </div>

          <div v-if="!loginState" class="flex items-center justify-center rounded-xl border border-dashed border-slate-700 p-6">
            <p class="text-sm text-slate-500">先保存网关配置，再发起登录</p>
          </div>
          <div v-else class="flex items-start gap-4 rounded-xl border border-slate-700 bg-slate-950/60 p-5">
            <template v-if="loginState.status === 'pending' && loginState.qrcodeUrl">
              <QrCode :value="loginState.qrcodeUrl" :size="160" />
              <div class="min-w-0 text-sm">
                <p class="text-slate-300">用手机微信扫码完成登录</p>
                <p v-if="loginState.message" class="mt-1 text-xs text-slate-500">{{ loginState.message }}</p>
              </div>
            </template>
            <p v-else-if="loginState.status === 'success'" class="text-emerald-300">✅ 登录成功</p>
            <p v-else class="text-red-300">登录失败：{{ loginState.message }}</p>
          </div>

          <button
            class="w-full rounded-xl bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-indigo-500/25 transition hover:opacity-90 disabled:opacity-50"
            :disabled="busy"
            @click="startLogin"
          >{{ loginState ? "重新获取二维码" : "保存并扫码登录" }}</button>
        </div>
      </template>

      <!-- 步骤 3：完成 -->
      <template v-else>
        <h2 class="text-lg font-semibold text-slate-100">③ 完成</h2>
        <p class="mt-2 text-sm text-slate-400">最小配置已完成。接下来可在控制台查看账号、聊天调试、日志与设置。</p>
        <ul class="mt-4 space-y-1 text-sm text-slate-300">
          <li>· LLM：{{ fields.llm.base_url }} / {{ fields.llm.model }}</li>
          <li>· 网关：{{ fields.openclaw.gateway_url }}</li>
          <li>· 账号：已登录 {{ loginState?.status === "success" ? "成功" : "待登录" }}</li>
        </ul>
        <button
          class="mt-6 w-full rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-emerald-500/25 transition hover:opacity-90 disabled:opacity-50"
          :disabled="busy"
          @click="finish"
        >进入控制台</button>
      </template>

      <div class="mt-6 flex items-center justify-between">
        <button v-if="step > 1" class="text-sm text-slate-500 hover:text-slate-300" @click="step -= 1">上一步</button>
        <span class="text-xs text-slate-600">第 {{ step }} / 3 步</span>
        <button v-if="step < 3" class="rounded-lg bg-slate-800 px-4 py-2 text-sm text-slate-200 hover:bg-slate-700 disabled:opacity-50" :disabled="busy" @click="next">下一步</button>
      </div>

      <p v-if="error" class="mt-3 text-xs text-red-300">{{ error }}</p>
      <p v-if="notice" class="mt-3 text-xs text-emerald-300">{{ notice }}</p>
    </section>
    </div>
  </div>
</template>
