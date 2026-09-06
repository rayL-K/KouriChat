<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import QRCode from "qrcode";

const props = defineProps<{ value: string; size?: number }>();
const url = ref("");

async function render() {
  if (!props.value) {
    url.value = "";
    return;
  }
  try {
    url.value = await QRCode.toDataURL(props.value, {
      width: props.size ?? 176,
      margin: 1,
      color: { dark: "#0f172a", light: "#ffffff" },
    });
  } catch {
    url.value = "";
  }
}

onMounted(render);
watch(() => props.value, render);
</script>

<template>
  <img
    v-if="url"
    :src="url"
    alt="登录二维码"
    class="shrink-0 rounded-xl border border-slate-700 bg-white object-contain p-1.5"
    :style="{ width: (size ?? 176) + 'px', height: (size ?? 176) + 'px' }"
  />
  <div
    v-else
    class="flex shrink-0 items-center justify-center rounded-xl border border-slate-700 bg-slate-800/40 text-xs text-slate-500"
    :style="{ width: (size ?? 176) + 'px', height: (size ?? 176) + 'px' }"
  >二维码生成中…</div>
</template>
