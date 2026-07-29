const form = document.querySelector("#controlForm");
const logs = document.querySelector("#logs");
const statusPill = document.querySelector("#statusPill");
const processMeta = document.querySelector("#processMeta");
const commandPreview = document.querySelector("#commandPreview");
const startButton = document.querySelector("#startButton");
const pauseButton = document.querySelector("#pauseButton");
const stopButton = document.querySelector("#stopButton");
const clearLogsButton = document.querySelector("#clearLogsButton");
const exportLogsButton = document.querySelector("#exportLogsButton");
const saveConfigButton = document.querySelector("#saveConfigButton");
const clearConfigButton = document.querySelector("#clearConfigButton");
const testBarkButton = document.querySelector("#testBarkButton");

const CONFIG_STORAGE_KEY = "videoMonitorConsole.config.v1";

const fields = {
  url: document.querySelector("#url"),
  browserChannel: document.querySelector("#browserChannel"),
  monitorInterval: document.querySelector("#monitorInterval"),
  playbackRate: document.querySelector("#playbackRate"),
  noVideoNextDelay: document.querySelector("#noVideoNextDelay"),
  nextSelector: document.querySelector("#nextSelector"),
  barkUrl: document.querySelector("#barkUrl"),
  autoLogin: document.querySelector("#autoLogin"),
  rememberPassword: document.querySelector("#rememberPassword"),
  loginPhone: document.querySelector("#loginPhone"),
  loginPassword: document.querySelector("#loginPassword"),
  autoPlay: document.querySelector("#autoPlay"),
  playSequential: document.querySelector("#playSequential"),
  muteBeforeAutoPlay: document.querySelector("#muteBeforeAutoPlay"),
  notifySectionComplete: document.querySelector("#notifySectionComplete"),
  notifyAllComplete: document.querySelector("#notifyAllComplete"),
};

let eventSource = null;
let lastLogId = 0;
let currentStatus = null;

fields.autoLogin.checked = true;

function normalizeBrowserChannel(value) {
  return ["msedge", "chrome"].includes(value) ? value : "msedge";
}

function readConfig() {
  const playbackRate = fields.playbackRate.value.trim();
  const nextSelector = fields.nextSelector.value.trim();

  return {
    url: fields.url.value.trim(),
    browserChannel: normalizeBrowserChannel(fields.browserChannel.value),
    monitorInterval: Number(fields.monitorInterval.value),
    autoLogin: fields.autoLogin.checked,
    rememberPassword: fields.rememberPassword.checked,
    loginPhone: fields.loginPhone.value.trim(),
    loginPassword: fields.loginPassword.value,
    autoPlay: fields.autoPlay.checked,
    muteBeforeAutoPlay: fields.muteBeforeAutoPlay.checked,
    playSequential: fields.playSequential.checked,
    nextSelector: nextSelector || null,
    noVideoNextDelay: Number(fields.noVideoNextDelay.value),
    playbackRate: playbackRate === "" ? null : Number(playbackRate),
    barkUrl: fields.barkUrl.value.trim(),
    notifySectionComplete: fields.notifySectionComplete.checked,
    notifyAllComplete: fields.notifyAllComplete.checked,
  };
}

function buildRuntimeConfig(config) {
  const { rememberPassword, ...runtimeConfig } = config;
  return runtimeConfig;
}

function writeFieldValue(field, value) {
  if (value === undefined) {
    return;
  }

  if (field.type === "checkbox") {
    field.checked = Boolean(value);
    return;
  }

  field.value = value === null ? "" : String(value);
}

function applySavedConfig(savedConfig) {
  const savedFields = savedConfig && typeof savedConfig === "object" ? savedConfig.fields : null;
  if (!savedFields || typeof savedFields !== "object") {
    return false;
  }

  writeFieldValue(fields.url, savedFields.url);
  writeFieldValue(fields.browserChannel, normalizeBrowserChannel(savedFields.browserChannel));
  writeFieldValue(fields.monitorInterval, savedFields.monitorInterval);
  writeFieldValue(fields.playbackRate, savedFields.playbackRate);
  writeFieldValue(fields.noVideoNextDelay, savedFields.noVideoNextDelay);
  writeFieldValue(fields.nextSelector, savedFields.nextSelector);
  writeFieldValue(fields.barkUrl, savedFields.barkUrl);
  writeFieldValue(fields.autoLogin, savedFields.autoLogin);
  writeFieldValue(fields.rememberPassword, savedFields.rememberPassword);
  writeFieldValue(fields.loginPhone, savedFields.loginPhone);
  if (savedFields.rememberPassword) {
    writeFieldValue(fields.loginPassword, savedFields.loginPassword);
  }
  writeFieldValue(fields.autoPlay, savedFields.autoPlay);
  writeFieldValue(fields.playSequential, savedFields.playSequential);
  writeFieldValue(fields.muteBeforeAutoPlay, savedFields.muteBeforeAutoPlay);
  writeFieldValue(fields.notifySectionComplete, savedFields.notifySectionComplete);
  writeFieldValue(fields.notifyAllComplete, savedFields.notifyAllComplete);

  return true;
}

function loadSavedConfig() {
  try {
    const rawConfig = window.localStorage.getItem(CONFIG_STORAGE_KEY);
    if (!rawConfig) {
      return;
    }

    if (applySavedConfig(JSON.parse(rawConfig))) {
      appendSystemLine("已加载本地保存的配置。");
    }
  } catch (error) {
    appendSystemLine("读取本地配置失败。");
  }
}

function saveConfig() {
  const config = readConfig();
  const savedFields = { ...config };
  if (!config.rememberPassword) {
    savedFields.loginPassword = "";
  }

  try {
    window.localStorage.setItem(
      CONFIG_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        savedAt: Date.now(),
        fields: savedFields,
      }),
    );
    appendSystemLine(config.rememberPassword ? "配置已保存，包含密码。" : "配置已保存，未保存密码。");
  } catch (error) {
    appendSystemLine("保存配置失败。");
  }
}

function clearSavedConfig() {
  try {
    window.localStorage.removeItem(CONFIG_STORAGE_KEY);
    appendSystemLine("已清除本地保存的配置。");
  } catch (error) {
    appendSystemLine("清除本地配置失败。");
  }
}

function validateConfig(config) {
  if (!config.url) {
    return "课程 URL 不能为空。";
  }
  if (!Number.isFinite(config.monitorInterval) || config.monitorInterval <= 0) {
    return "检测间隔必须大于 0。";
  }
  if (!Number.isFinite(config.noVideoNextDelay) || config.noVideoNextDelay < 0) {
    return "无视频等待必须大于或等于 0。";
  }
  if (config.autoLogin && !config.loginPhone) {
    return "启用自动登录时，手机号不能为空。";
  }
  if (config.autoLogin && !config.loginPassword) {
    return "启用自动登录时，密码不能为空。";
  }
  if (config.playbackRate !== null && (!Number.isFinite(config.playbackRate) || config.playbackRate <= 0)) {
    return "播放倍速必须大于 0。";
  }
  if (config.playSequential && !config.autoPlay) {
    return "顺序播放需要同时启用自动播放。";
  }
  if ((config.notifySectionComplete || config.notifyAllComplete) && !config.barkUrl) {
    return "启用 Bark 提醒时，Bark Key 或 URL 不能为空。";
  }

  return null;
}

function shellQuote(value) {
  if (value === "") {
    return "''";
  }
  if (/^[A-Za-z0-9_./:=#?-]+$/.test(value)) {
    return value;
  }
  return `'${value.replaceAll("'", "'\"'\"'")}'`;
}

function buildPreview(config) {
  const command = [
    "python3",
    "main.py",
    "--url",
    config.url ? config.url : "<URL>",
    "--browser-channel",
    config.browserChannel,
    "--monitor-interval",
    String(config.monitorInterval || 2),
    "--no-video-next-delay",
    String(Number.isFinite(config.noVideoNextDelay) ? config.noVideoNextDelay : 3),
  ];

  if (config.autoPlay) {
    command.push("--auto-play");
  }
  if (config.autoLogin) {
    command.push("--auto-login");
  }
  if (config.muteBeforeAutoPlay) {
    command.push("--mute-before-auto-play");
  }
  if (config.playSequential) {
    command.push("--play-sequential");
  }
  if (config.nextSelector) {
    command.push("--next-selector", config.nextSelector);
  }
  if (config.playbackRate !== null && Number.isFinite(config.playbackRate)) {
    command.push("--playback-rate", String(config.playbackRate));
  }
  if (config.notifySectionComplete) {
    command.push("--notify-section-complete");
  }
  if (config.notifyAllComplete) {
    command.push("--notify-all-complete");
  }

  return command.map(shellQuote).join(" ");
}

function updatePreview() {
  commandPreview.textContent = buildPreview(readConfig());
}

function updateDependentControls() {
  if (!fields.autoPlay.checked) {
    fields.playSequential.checked = false;
  }
  fields.playSequential.disabled = !fields.autoPlay.checked;
  updatePreview();
}

function appendLog(entry) {
  const line = document.createElement("span");
  const stream = entry.stream === "system" ? "system" : "main";
  line.className = entry.stream === "system" ? "log-line-system" : "";
  line.textContent = `[${entry.timestamp}] ${stream} ${entry.line}\n`;
  logs.appendChild(line);

  while (logs.childElementCount > 1000) {
    logs.removeChild(logs.firstElementChild);
  }

  logs.scrollTop = logs.scrollHeight;
  if (entry.id) {
    lastLogId = Math.max(lastLogId, entry.id);
  }
}

function appendSystemLine(line) {
  appendLog({
    timestamp: new Date().toLocaleTimeString("zh-CN", { hour12: false }),
    stream: "system",
    line,
  });
}

function normalizeBarkUrl(value) {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) {
    return null;
  }
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
    return trimmed;
  }
  return `https://api.day.app/${encodeURIComponent(trimmed.replace(/^\/+/, ""))}`;
}

function buildBarkPushUrl(barkUrl, title, body) {
  const normalized = normalizeBarkUrl(barkUrl);
  if (!normalized) {
    return null;
  }

  const url = new URL(normalized);
  url.pathname = `${url.pathname.replace(/\/+$/, "")}/${encodeURIComponent(title)}/${encodeURIComponent(body)}`;
  url.searchParams.set("isArchive", "1");
  return url.toString();
}

function downloadTextFile(filename, text) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

function timestampForFilename() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return [
    now.getFullYear(),
    pad(now.getMonth() + 1),
    pad(now.getDate()),
    "-",
    pad(now.getHours()),
    pad(now.getMinutes()),
    pad(now.getSeconds()),
  ].join("");
}

async function exportLogs() {
  try {
    const response = await fetch("/api/logs/export");
    if (response.ok) {
      const text = await response.text();
      downloadTextFile(`video-monitor-logs-${timestampForFilename()}.txt`, text);
      appendSystemLine("日志已导出。");
      return;
    }
  } catch (error) {
    // Fall back to the visible log window below.
  }

  const visibleLogs = logs.textContent.trim();
  const text = visibleLogs || "当前页面没有可导出的日志。";
  downloadTextFile(`video-monitor-visible-logs-${timestampForFilename()}.txt`, `${text}\n`);
  appendSystemLine("已导出当前页面可见日志。");
}

function sendBarkTestWithImage(barkUrl) {
  return new Promise((resolve) => {
    const pushUrl = buildBarkPushUrl(
      barkUrl,
      "视频控制台：测试推送",
      `Bark 测试推送请求已发出。\n${new Date().toLocaleString("zh-CN", { hour12: false })}`,
    );
    if (!pushUrl) {
      resolve(false);
      return;
    }

    const image = new Image();
    const finish = () => resolve(true);
    image.onload = finish;
    image.onerror = finish;
    image.src = pushUrl;
    setTimeout(finish, 3000);
  });
}

async function testBarkNotification() {
  const barkUrl = fields.barkUrl.value.trim();
  if (!barkUrl) {
    appendSystemLine("Bark Key 或 URL 不能为空。");
    return;
  }

  testBarkButton.disabled = true;
  const originalText = testBarkButton.textContent;
  testBarkButton.textContent = "发送中";

  try {
    try {
      const response = await fetch("/api/bark/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barkUrl }),
      });

      if (response.ok) {
        appendSystemLine("Bark 测试推送已发送，请查看手机。");
        return;
      }

      if (response.status !== 404) {
        const body = await response.json().catch(() => ({ detail: "Bark 测试推送失败。" }));
        appendSystemLine(typeof body.detail === "string" ? body.detail : "Bark 测试推送失败。");
        return;
      }
    } catch (error) {
      // The fallback below still sends a local browser request.
    }

    const sent = await sendBarkTestWithImage(barkUrl);
    appendSystemLine(sent ? "Bark 测试推送请求已发出，请查看手机。" : "Bark 测试推送失败。");
  } finally {
    testBarkButton.disabled = false;
    testBarkButton.textContent = originalText;
  }
}

function applyStatus(status) {
  currentStatus = status;
  statusPill.classList.remove("status-idle", "status-running", "status-paused", "status-stopped");

  if (status.running) {
    if (status.paused) {
      statusPill.textContent = "已暂停";
      statusPill.classList.add("status-paused");
    } else {
      statusPill.textContent = "运行中";
      statusPill.classList.add("status-running");
    }
    startButton.disabled = true;
    pauseButton.disabled = false;
    pauseButton.textContent = status.paused ? "继续" : "暂停";
    stopButton.disabled = false;
    const started = status.startedAt ? new Date(status.startedAt * 1000).toLocaleTimeString("zh-CN", { hour12: false }) : "";
    processMeta.textContent = `PID ${status.pid || "-"} · ${started}${status.paused ? " · 已暂停" : ""}`;
  } else {
    startButton.disabled = false;
    pauseButton.disabled = true;
    pauseButton.textContent = "暂停";
    stopButton.disabled = true;

    if (status.exitCode === null || status.exitCode === undefined) {
      statusPill.textContent = "未运行";
      statusPill.classList.add("status-idle");
      processMeta.textContent = "等待启动";
    } else {
      statusPill.textContent = "已停止";
      statusPill.classList.add("status-stopped");
      processMeta.textContent = `退出码 ${status.exitCode}`;
    }
  }

  if (status.command) {
    commandPreview.textContent = status.command;
  } else {
    updatePreview();
  }
}

async function fetchStatus() {
  const response = await fetch("/api/status");
  if (!response.ok) {
    throw new Error("Status request failed.");
  }
  applyStatus(await response.json());
}

function connectLogs(resetCursor = false) {
  if (eventSource) {
    eventSource.close();
  }
  if (resetCursor) {
    lastLogId = 0;
  }

  eventSource = new EventSource(`/api/logs?after=${lastLogId}`);
  eventSource.addEventListener("log", (event) => {
    appendLog(JSON.parse(event.data));
  });
  eventSource.addEventListener("status", (event) => {
    applyStatus(JSON.parse(event.data));
  });
  eventSource.onerror = () => {
    processMeta.textContent = "日志连接重试中";
  };
}

async function startMonitor(event) {
  event.preventDefault();

  const config = readConfig();
  const error = validateConfig(config);
  if (error) {
    appendSystemLine(error);
    return;
  }

  logs.textContent = "";
  lastLogId = 0;

  const response = await fetch("/api/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildRuntimeConfig(config)),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "启动失败。" }));
    appendSystemLine(typeof body.detail === "string" ? body.detail : "启动失败。");
    await fetchStatus().catch(() => undefined);
    return;
  }

  applyStatus(await response.json());
  connectLogs(true);
}

async function stopMonitor() {
  const response = await fetch("/api/stop", { method: "POST" });
  if (!response.ok) {
    appendSystemLine("停止失败。");
    return;
  }
  applyStatus(await response.json());
}

async function togglePauseMonitor() {
  const endpoint = currentStatus && currentStatus.paused ? "/api/resume" : "/api/pause";
  const response = await fetch(endpoint, { method: "POST" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "暂停切换失败。" }));
    appendSystemLine(typeof body.detail === "string" ? body.detail : "暂停切换失败。");
    await fetchStatus().catch(() => undefined);
    return;
  }
  applyStatus(await response.json());
}

form.addEventListener("submit", startMonitor);
pauseButton.addEventListener("click", togglePauseMonitor);
stopButton.addEventListener("click", stopMonitor);
saveConfigButton.addEventListener("click", saveConfig);
clearConfigButton.addEventListener("click", clearSavedConfig);
testBarkButton.addEventListener("click", testBarkNotification);
exportLogsButton.addEventListener("click", exportLogs);
clearLogsButton.addEventListener("click", () => {
  logs.textContent = "";
});

for (const field of Object.values(fields)) {
  field.addEventListener("input", updatePreview);
  field.addEventListener("change", updatePreview);
}

fields.autoPlay.addEventListener("change", updateDependentControls);

loadSavedConfig();
updateDependentControls();
fetchStatus().catch(() => appendSystemLine("状态接口不可用。"));
connectLogs();
