<script setup lang="ts">
import { ref } from "vue";
import { api, type LoginState, type Status } from "../api";
import QrCode from "../components/QrCode.vue";

const props = defineProps<{ status: Status | null }>();
const emit = defineEmits<{ changed: [] }>();

const busy = ref(false);
const error = ref("");
const notice = ref("");

async function startLogin() {
  busy.value = true;
  error.value = "";
  try {
    await api.login();
    emit("changed");
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    busy.value = false;
  }
}

async function relogin(accountId: string) {
  busy.value = true;
  error.value = "";
  try {
    await api.relogin(accountId);
    emit("changed");
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    busy.value = false;
  }
}

async function logout(accountId: string) {
  if (!window.confirm(`本地登出账号 ${accountId}？（网关侧凭据需 CLI 清理）`)) return;
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    const res = await api.logout(accountId);
    notice.value = res.note ?? "已登出";
    emit("changed");
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    busy.value = false;
  }
}

function loginBadge(state: LoginState) {
  if (state.status === "success") return { text: "登录成功", cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" };
  if (state.status === "failed") return { text: "登录失败", cls: "bg-red-500/15 text-red-300 border-red-500/30" };
  return { text: "待扫码", cls: "bg-amber-500/15 text-amber-300 border-amber-500/30" };
}

const statusBadge: Record<string, string> = {
  online: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  invalid: "bg-red-500/15 text-red-300 border-red-500/30",
  offline: "bg-slate-600/30 text-slate-300 border-slate-600/40",
};
const statusDot: Record<string, string> = {
  online: "bg-emerald-400",
  invalid: "bg-red-400",
  offline: "bg-slate-400",
};
</script>

<template>
  <div class="grid gap-6 lg:grid-cols-2">
    <!-- 扫码登录 -->
    <section class="card p-5">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold text-slate-300">扫码登录</h2>
        <span v-if="status?.login" class="rounded-full border px-2 py-0.5 text-xs" :class="loginBadge(status.login).cls">{{ loginBadge(status.login).text }}</span>
      </div>

      <template v-if="!status?.login">
        <p class="mt-3 text-sm text-slate-400">通过 weixin-gateway 的 /login 获取二维码，用手机微信扫码完成登录。</p>
        <button
          class="mt-4 inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-indigo-500/25 transition hover:opacity-90 disabled:opacity-50"
          :disabled="busy"
          @click="startLogin"
        >
          <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM17 17h3v3h-3zM14 20h3M20 14h3"/></svg>
          {{ busy ? "请求中…" : "发起扫码登录" }}
        </button>
      </template>

      <template v-else>
        <div class="mt-4 flex items-start gap-4">
          <QrCode
            v-if="status.login.status === 'pending'"
            :value="status.login.qrcodeUrl"
            :size="176"
          />
          <div class="min-w-0 text-sm">
            <p class="text-slate-300">用手机微信扫描左侧二维码完成登录</p>
            <a
              v-if="status.login.status === 'pending' && status.login.qrcodeUrl"
              :href="status.login.qrcodeUrl"
              target="_blank"
              rel="noopener"
              class="mt-2 block break-all text-xs text-indigo-400 hover:underline"
            >{{ status.login.qrcodeUrl }}</a>
            <p v-if="status.login.message" class="mt-2 text-xs text-slate-400">{{ status.login.message }}</p>
            <p v-if="status.login.status === 'failed'" class="mt-2 text-xs text-amber-300">二维码可能已失效，可点击下方重新获取。</p>
            <button v-if="status.login.status === 'failed'" class="mt-3 rounded-lg bg-slate-800 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700" @click="startLogin">重新获取二维码</button>
          </div>
        </div>
      </template>

      <p v-if="error" class="mt-3 text-xs text-red-300">{{ error }}</p>
      <p v-if="notice" class="mt-3 text-xs text-emerald-300">{{ notice }}</p>
    </section>

    <!-- 账号列表 -->
    <section class="card p-5">
      <h2 class="text-sm font-semibold text-slate-300">已登录账号（本地镜像）</h2>
      <div v-if="!status?.accounts.length" class="mt-4 rounded-xl border border-dashed border-slate-700 p-6 text-center text-sm text-slate-500">
        暂无敌账号，先在左侧扫码登录。
      </div>
      <ul class="mt-3 space-y-3">
        <li
          v-for="acc in status?.accounts"
          :key="acc.accountId"
          class="rounded-xl border border-slate-800 bg-slate-950/60 p-4"
        >
          <div class="flex flex-wrap items-center gap-2">
            <span class="flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs" :class="statusBadge[acc.status] ?? statusBadge.offline">
              <span class="h-1.5 w-1.5 rounded-full" :class="statusDot[acc.status] ?? statusDot.offline"></span>
              {{ acc.status }}
            </span>
            <code class="text-sm font-medium text-slate-100">{{ acc.accountId }}</code>
            <span v-if="acc.userId" class="text-xs text-slate-500">userId: {{ acc.userId }}</span>
          </div>
          <div class="mt-3 flex gap-2">
            <button
              v-if="acc.status === 'invalid'"
              class="rounded-lg bg-amber-600/90 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-500 disabled:opacity-50"
              :disabled="busy"
              @click="relogin(acc.accountId)"
            >重新登录</button>
            <button
              class="rounded-lg bg-slate-800 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700 disabled:opacity-50"
              :disabled="busy"
              @click="logout(acc.accountId)"
            >登出</button>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>
