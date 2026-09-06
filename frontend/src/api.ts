/** 与 kourichat.webui 插件（T17）的 JSON API 契约一一对应。 */

export interface Account {
  accountId: string;
  userId: string;
  baseUrl?: string;
  status: "online" | "invalid" | "offline";
  savedAt?: number;
}

export interface LoginState {
  uid: string;
  qrcodeUrl: string;
  accountId?: string;
  status: "pending" | "success" | "failed";
  message?: string;
}

export interface Status {
  connected: boolean;
  gateway_url: string;
  accounts: Account[];
  login: LoginState | null;
  needs_relogin: string[];
}

export interface LogRow {
  time: string;
  level: string;
  line: string;
}

export interface SettingsFields {
  core: { log_level: string };
  openclaw: {
    gateway_url: string;
    access_token: string;
    data_dir: string;
    autologin: boolean;
    poll_interval: number;
  };
  llm: { base_url: string; api_key: string; model: string; data_dir: string };
  webui: { host: string; port: number };
  persona: { personas_dir: string; enable: string };
  echo: { enabled: boolean };
}

export interface Dashboard {
  connected: boolean;
  accounts: Account[];
  login: LoginState | null;
  personas: { count: number; active: string | null };
  first_run: boolean;
}

export interface ApiError {
  ok?: boolean;
  error?: string;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const data = (await res.json().catch(() => ({}))) as T & ApiError;
  if (!res.ok) {
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  return data;
}

export const api = {
  status: () => req<Status>("/api/openclaw/status"),
  login: (accountId?: string) =>
    req<LoginState>("/api/openclaw/login", {
      method: "POST",
      body: JSON.stringify({ accountId: accountId || undefined }),
    }),
  relogin: (accountId: string) =>
    req<LoginState>("/api/openclaw/relogin", {
      method: "POST",
      body: JSON.stringify({ accountId }),
    }),
  logout: (accountId: string) =>
    req<{ ok: boolean; note?: string }>("/api/openclaw/logout", {
      method: "POST",
      body: JSON.stringify({ accountId }),
    }),
  chatSend: (payload: { channel_id: string; channel_type: "private"; text: string }) =>
    req<{ ok: boolean; message_id: string }>("/api/chat/send", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  chatMock: (text: string, channelType: "private" = "private") =>
    req<{ ok: boolean }>("/api/chat/mock", {
      method: "POST",
      body: JSON.stringify({ text, channel_type: channelType }),
    }),
  logs: (limit = 200, level = "DEBUG") =>
    req<{ logs: LogRow[] }>(`/api/logs?limit=${limit}&level=${level}`),
  settingsGet: () =>
    req<{ ok: boolean; fields: SettingsFields }>("/api/settings"),
  settingsSave: (fields: SettingsFields) =>
    req<{ ok: boolean; note?: string }>("/api/settings", {
      method: "POST",
      body: JSON.stringify({ fields }),
    }),
  setupStatus: () => req<{ ok: boolean; first_run: boolean }>("/api/setup/status"),
  dashboard: () => req<Dashboard>("/api/dashboard"),
  llmTest: (llm: SettingsFields["llm"]) =>
    req<{ ok: boolean; reply?: string; model?: string; note?: string; error?: string }>("/api/llm/test", {
      method: "POST",
      body: JSON.stringify({ llm }),
    }),
};
