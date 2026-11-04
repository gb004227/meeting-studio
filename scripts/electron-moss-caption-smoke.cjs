const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");

module.exports = async function ({ win, runtime, app, getState }) {
  const directory = path.resolve(__dirname, "..", "artifacts");
  fs.mkdirSync(directory, { recursive: true });
  const js = (source) => win.webContents.executeJavaScript(source, true);
  const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function wait(check, label, timeout = 45000) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      if (await check()) return;
      await pause(100);
    }
    throw new Error("MOSS caption smoke timeout: " + label);
  }
  const click = (label) =>
    js(
      `(()=>{const button=[...document.querySelectorAll('button')].find(element=>element.textContent.trim()===${JSON.stringify(label)});if(!button)throw new Error('Button missing');button.click()})()`,
    );
  async function json(route) {
    return (
      await fetch(runtime.baseUrl + route, {
        headers: { "x-meeting-token": runtime.token },
      })
    ).json();
  }
  await wait(
    () => js("!!document.querySelector('.dashboard .mode-grid')"),
    "dashboard",
  );
  const settings=await json("/api/settings");
  assert.equal(settings.secrets.doubao_api_key, false);
  const bundled=process.env.MEETING_SMOKE_BUNDLED==='1';
  if (bundled) {
    const resources=path.resolve(__dirname,'..');
    assert.equal(path.resolve(settings.moss_path),path.join(resources,'models','MOSS-Transcribe-Diarize'));
    assert.equal(path.resolve(settings.moss_python),path.join(resources,'moss-python','python.exe'));
    assert.ok(settings.moss_ready&&settings.local_live_ready&&settings.speaker_helper_ready);
  }
  await click("新建录音");
  await wait(
    () => js("!!document.querySelector('.engine-choices')"),
    "engine selector",
  );
  await js(
    "document.querySelector('.engine-choices button:nth-child(2)').click()",
  );
  const requested = Date.now();
  await click("开始录音");
  await wait(() => getState().active, "recording active");
  const started = Date.now();
  const mid = getState().meetingId;
  await wait(
    () =>
      js(
        "(document.querySelector('.provisional p')?.textContent.trim().length||0)>1",
      ),
    "caption visible before stopping",
    90000,
  );
  const first = (Date.now() - started) / 1000;
  const fromButton = (Date.now() - requested) / 1000;
  const captionAudioMs = getState().elapsed;
  console.log(JSON.stringify({stage:'live caption',seconds:first,audio_ms:getState().elapsed}));
  assert.ok(getState().active, "caption must arrive during capture");
  const during = await json("/api/meetings/" + mid);
  assert.equal(during.engine, "moss");
  assert.equal(during.status, "recording");
  await pause(250);
  await js(
    "new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))",
  );
  fs.writeFileSync(
    path.join(directory, "moss-live-caption.png"),
    (await win.webContents.capturePage()).toPNG(),
  );
  await wait(() => getState().elapsed >= 8000, 'enough speech for final refinement');
  await click("结束录音");
  const stopping = Date.now();
  await wait(() => !getState().active && getState().saved, "audio saved");
  const saveSeconds = (Date.now() - stopping) / 1000;
  console.log(JSON.stringify({stage:'saved',seconds:saveSeconds}));
  await wait(
    async () => {
      const detail=await json("/api/meetings/"+mid);
      if (detail.status==='failed'||detail.status==='partial_failed') throw new Error(detail.error||'Local refinement failed');
      return !!detail.minutes;
    },
    "full local refinement",
    300000,
  );
  const meeting = await json("/api/meetings/" + mid);
  assert.equal(meeting.error, "");
  assert.ok(meeting.segments.length);
  const report = {
    status: "PASS",
    engine: "moss",
    bundled_local_runtime: bundled,
    asr_key_configured: false,
    source: "Chromium synthetic microphone; no physical microphone or cloud",
    first_caption_seconds_from_capture: Math.round(first * 100) / 100,
    first_caption_seconds_from_start_button: Math.round(fromButton * 100) / 100,
    first_caption_audio_ms: captionAudioMs,
    captions_visible_before_stop: true,
    recording_ms: meeting.duration_ms,
    save_seconds: Math.round(saveSeconds * 100) / 100,
    final_segments: meeting.segments.length,
    checks: [
      "MOSS selected",
      "local streaming captions visible during recording",
      "no ASR key configured",
      "stop and save",
      "full local refinement",
      "minutes generated",
    ],
  };
  fs.writeFileSync(
    path.join(directory, "moss-desktop-smoke.json"),
    JSON.stringify(report, null, 2),
  );
  app.quit();
};
