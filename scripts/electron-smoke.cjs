const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");

module.exports = async function ({ win, runtime, app, getState, getCompact }) {
  const output = path.resolve(__dirname, "..", "artifacts");
  fs.mkdirSync(output, { recursive: true });
  const errors = [];
  win.webContents.on("console-message", (_event, details) => {
    const message =
      typeof details === "object" ? details.message : String(details);
    if (/Uncaught|TypeError|ReferenceError/.test(message))
      errors.push(message.replaceAll(runtime.token, "[session-token]"));
  });
  const delay = (ms) => new Promise((r) => setTimeout(r, ms));
  const js = (source) => win.webContents.executeJavaScript(source, true);
  async function wait(fn, label, timeout = 30000) {
    const started = Date.now();
    while (Date.now() - started < timeout) {
      if (await fn()) return;
      await delay(150);
    }
    throw new Error("Desktop smoke timeout: " + label);
  }
  async function shot(name, window = win) {
    await delay(350);
    await window.webContents.executeJavaScript(
      "new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))",
    );
    const capture = await window.webContents.capturePage();
    fs.writeFileSync(path.join(output, name + ".png"), capture.toPNG());
  }
  const clickText = (label) =>
    js(
      `(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(label)});if(!b)throw new Error('Button not found: '+${JSON.stringify(label)});b.click();})()`,
    );
  async function json(route) {
    const r = await fetch(runtime.baseUrl + route, {
      headers: { "x-meeting-token": runtime.token },
    });
    if (!r.ok) throw new Error("Local API " + r.status);
    return r.json();
  }
  await wait(
    () => js(`!!document.querySelector('.dashboard .mode-grid')`),
    "dashboard ready",
  );
  await shot("desktop-home");
  await clickText("设置");
  await wait(
    () => js(`!!document.querySelector('.settings-card .input-icon')`),
    "settings ready",
  );
  assert.equal((await json("/api/settings")).secrets.doubao_api_key, true);
  await shot("desktop-settings");
  await clickText("工作台");
  await clickText("新建录音");
  await wait(
    () => js(`!!document.querySelector('.modal')`),
    "new recording dialog",
  );
  await js(
    `(()=>{const input=document.querySelector('.modal .field input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'桌面联调 · 合成语音');input.dispatchEvent(new Event('input',{bubbles:true}));})()`,
  );
  await clickText("开始录音");
  await wait(() => getState().active, "synthetic microphone recording", 30000);
  const mid = getState().meetingId;
  await wait(() => getState().elapsed >= 4500, "PCM frames reach backend");
  await wait(
    () => js(`!!document.querySelector('.person-row')`),
    "real cloud speaker result",
    45000,
  );
  await js(`document.querySelector('.person-row').click()`);
  await wait(
    () =>
      js(`document.querySelector('.modal h2')?.textContent==='修改说话人姓名'`),
    "speaker rename dialog",
  );
  await js(
    `(()=>{const input=document.querySelector('.modal input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'测试主持人');input.dispatchEvent(new Event('input',{bubbles:true}));})()`,
  );
  await clickText("保存姓名");
  await wait(
    () =>
      js(
        `!document.querySelector('.modal')&&document.body.textContent.includes('测试主持人')`,
      ),
    "rename applied during recording",
  );
  await shot("desktop-recording");
  await js(
    `document.querySelector('.recording-panel .row > button:nth-child(2)').click()`,
  );
  await wait(() => getState().paused, "pause");
  const before = getState().elapsed;
  await delay(650);
  assert.ok(
    Math.abs(getState().elapsed - before) <= 200,
    "pause must stop recorded sample count",
  );
  await clickText("收起");
  await wait(() => getCompact(), "compact window created");
  const small = getCompact();
  await wait(
    () =>
      small.webContents.executeJavaScript(
        `!!document.querySelector('.compact-shell')`,
      ),
    "compact UI ready",
  );
  assert.ok(small.isAlwaysOnTop());
  await shot("desktop-compact", small);
  await small.webContents.executeJavaScript(
    `document.querySelector('button[aria-label="展开录音窗口"]').click()`,
    true,
  );
  await js(
    `document.querySelector('.recording-panel .row > button:nth-child(2)').click()`,
  );
  await wait(() => !getState().paused, "resume");
  await wait(
    () => getState().elapsed >= 22000,
    "streaming beyond the first 15 seconds",
    40000,
  );
  await clickText("结束录音");
  await wait(
    () => !getState().active && getState().saved,
    "recording safely saved",
    45000,
  );
  await wait(
    async () => !!(await json("/api/meetings/" + mid)).minutes,
    "minutes and actions generated",
    30000,
  );
  await wait(
    () => js(`!!document.querySelector('.completion-stats')`),
    "completion card",
  );
  await shot("desktop-saved");
  await clickText("查看会议");
  await js(
    `(()=>{const b=[...document.querySelectorAll('.content-tabs button')].find(b=>b.textContent.includes('智能纪要'));b.click();})()`,
  );
  await wait(
    () => js(`!!document.querySelector('.summary-list')`),
    "minutes UI",
  );
  await shot("desktop-minutes");
  const meeting = await json("/api/meetings/" + mid);
  assert.ok(meeting.segments.length > 0);
  assert.equal(
    meeting.speakers.length,
    1,
    "one synthetic voice should remain one person",
  );
  assert.equal(
    meeting.error,
    "",
    "recording should finish without missing-audio warnings",
  );
  assert.ok(
    meeting.segments.some((segment) => segment.end_ms >= 18000),
    "later audio must also reach the final transcript",
  );
  assert.ok(meeting.speakers.some((p) => p.name === "测试主持人"));
  const exported = await fetch(
    runtime.baseUrl + `/api/meetings/${mid}/export/txt`,
    { headers: { "x-meeting-token": runtime.token } },
  );
  assert.ok((await exported.text()).includes("测试主持人"));
  assert.equal(errors.length, 0, errors.join("\n"));
  const report = {
    status: "PASS",
    capture:
      "Chromium synthetic microphone from Windows SAPI fixture; no physical microphone capture",
    recording_ms: meeting.duration_ms,
    segments: meeting.segments.length,
    speakers: meeting.speakers.length,
    actions: meeting.minutes.data.action_items.length,
    checks: [
      "desktop startup",
      "settings credential masking",
      "real AudioWorklet PCM capture",
      "live ASR",
      "rename while recording",
      "pause sample clock",
      "compact always-on-top window",
      "resume",
      "streaming beyond 15 seconds",
      "stop and flush",
      "completion card",
      "minutes page",
      "saved name export",
    ],
    renderer_errors: errors,
  };
  fs.writeFileSync(
    path.join(output, "desktop-smoke.json"),
    JSON.stringify(report, null, 2),
  );
  process.stdout.write(JSON.stringify(report) + "\n");
  app.quit();
};
