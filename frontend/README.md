# KouriChat 控制台前端（Vue 3 + Vite + TS + Tailwind CSS）

工单 18。纯消费 `kourichat.webui` 插件（工单 17）的 JSON API；构建产物 `dist/`
由 webui 插件静态托管（默认 `static_dir = ./frontend/dist`）。

## 开发

```bash
npm install
npm run dev        # http://localhost:5173，/api 已 proxy 到 http://127.0.0.1:8080
```

先启动 kourichat（含 webui 插件，默认端口 8080），再启动 dev server 联调。

## 构建

```bash
npm run build      # 产出 dist/
npm run typecheck  # vue-tsc --noEmit
```

## 目录

- `src/api.ts`        —— 与 webui API 契约一一对应的类型化封装（status/login/relogin/logout/chatSend/chatMock/logs/configGet/configSave）
- `src/App.vue`       —— 顶栏（连接徽标/网关地址）+ 5 个 tab（总览/账号/聊天调试/日志/配置），3s 轮询 status
- `src/views/*.vue`   —— 各视图（扫码登录/账号卡片/聊天调试/日志/配置编辑）
