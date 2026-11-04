const {
  app,
  BrowserWindow,
  ipcMain,
  session,
  desktopCapturer,
  dialog,
  shell,
} = require("electron");
const { spawn } = require("node:child_process");
const { randomBytes } = require("node:crypto");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const fs = require("node:fs");
const net = require("node:net");

let mainWindow, recorderWindow, compactWindow, backend;
let runtime,
  recordingState = { active: false, paused: false, elapsed: 0, level: 0 };
const root = app.isPackaged
  ? process.resourcesPath
  : path.resolve(__dirname, "..");
const applicationRoot = app.isPackaged ? app.getAppPath() : root;
const token = randomBytes(32).toString("hex");
const preload = path.join(__dirname, "preload.cjs");
const dataDirectory =
  process.env.MEETING_DATA_DIR ||
  path.join(app.getPath("appData"), "..", "Local", "MeetingStudio");
fs.mkdirSync(dataDirectory, { recursive: true });
const smoke =
  process.env.MEETING_SMOKE === "1" && !!process.env.MEETING_FAKE_AUDIO;
if (smoke) {
  fs.mkdirSync(path.join(root, "artifacts"), { recursive: true });
  const profile = path.join(dataDirectory, "chromium-profile");
  fs.mkdirSync(profile, { recursive: true });
  app.setPath("userData", profile);
  app.commandLine.appendSwitch("use-fake-device-for-media-stream");
  app.commandLine.appendSwitch("use-fake-ui-for-media-stream");
  if (process.env.MEETING_FAKE_AUDIO)
    app.commandLine.appendSwitch(
      "use-file-for-fake-audio-capture",
      process.env.MEETING_FAKE_AUDIO,
    );
  app.disableHardwareAcceleration();
}

function broadcastState(value) {
  recordingState = { ...recordingState, ...value };
  for (const win of [mainWindow, compactWindow]) {
    if (win && !win.isDestroyed())
      win.webContents.send("recording:state", recordingState);
  }
  if (value.saved && mainWindow && !mainWindow.isDestroyed()) {
    if (!smoke) {
      mainWindow.show();
      mainWindow.focus();
    }
    if (compactWindow && !compactWindow.isDestroyed()) compactWindow.hide();
  }
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
  });
}

async function startBackend() {
  const port = await freePort();
  runtime = { baseUrl: `http://127.0.0.1:${port}`, token, dataDirectory };
  const python = app.isPackaged
    ? path.join(root, "python", "python.exe")
    : path.join(root, ".venv", "Scripts", "python.exe");
  if (!fs.existsSync(python))
    throw new Error("Python 运行环境不存在。请先运行“首次安装.cmd”。");
  const log = fs.openSync(path.join(dataDirectory, "backend.log"), "a");
  backend = spawn(
    python,
    [
      "-m",
      "uvicorn",
      "meeting_app.app:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
      "--no-access-log",
      "--log-level",
      "warning",
    ],
    {
      cwd: root,
      windowsHide: true,
      env: {
        ...process.env,
        PYTHONPATH: path.join(root, "backend"),
        PYTHONUTF8: "1",
        MEETING_TOKEN: token,
        MEETING_DATA_DIR: dataDirectory,
      },
      stdio: ["ignore", log, log],
    },
  );
  backend.once("exit", () => {
    if (!app.quitting && mainWindow && !mainWindow.isDestroyed())
      mainWindow.webContents.send(
        "backend:error",
        "本地服务已退出，请重新启动听会。已保存的会议仍在本机。",
      );
  });
  for (let attempt = 0; attempt < 120; attempt++) {
    try {
      if ((await fetch(runtime.baseUrl + "/health")).ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("本地服务启动超时。可在本机数据目录查看 backend.log。");
}

function createWindow(options = {}) {
  return new BrowserWindow({
    width: 1320,
    height: 900,
    minWidth: 1050,
    minHeight: 720,
    backgroundColor: "#f6f8fa",
    autoHideMenuBar: true,
    title: "听会",
    icon: path.join(__dirname, "icon.png"),
    show: false,
    webPreferences: {
      preload,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: false,
      autoplayPolicy: "no-user-gesture-required",
    },
    ...options,
  });
}

async function load(win, page = "index.html", hash = "") {
  const devUrl = process.env.MEETING_DEV_URL;
  if (devUrl) await win.loadURL(devUrl.replace(/\/$/, "") + "/" + page + hash);
  else {
    const address = pathToFileURL(path.join(applicationRoot, "dist", page));
    address.hash = hash.replace(/^#/, "");
    await win.loadURL(address.href);
  }
}

function registerIPC() {
  ipcMain.handle("runtime", () => runtime);
  ipcMain.handle("recording:get", () => recordingState);
  ipcMain.handle("recording:command", async (_event, command) => {
    if (!recorderWindow || recorderWindow.isDestroyed())
      throw new Error("录音控制器未就绪");
    recorderWindow.webContents.send("recording:command", command);
    return { ok: true };
  });
  ipcMain.on("recording:state", (_event, value) => broadcastState(value));
  ipcMain.handle("recording:compact", async () => {
    if (!compactWindow || compactWindow.isDestroyed()) {
      compactWindow = createWindow({
        width: 300,
        height: 66,
        minWidth: 300,
        minHeight: 66,
        maxWidth: 300,
        maxHeight: 66,
        frame: false,
        alwaysOnTop: true,
        resizable: false,
        skipTaskbar: true,
        transparent: true,
        backgroundColor: "#00000000",
      });
      await load(compactWindow, "index.html", "#compact");
    }
    if (!smoke) compactWindow.show();
    mainWindow.hide();
    return true;
  });
  ipcMain.handle("recording:expand", () => {
    if (!smoke) {
      mainWindow.show();
      mainWindow.focus();
    }
    if (compactWindow) compactWindow.hide();
  });
  ipcMain.handle("file:pick", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: "导入会议录音",
      properties: ["openFile"],
      filters: [
        {
          name: "音频与视频",
          extensions: [
            "wav",
            "mp3",
            "m4a",
            "aac",
            "flac",
            "ogg",
            "opus",
            "mp4",
            "mov",
            "mkv",
            "webm",
            "wma",
            "amr",
          ],
        },
      ],
    });
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle("file:export", async (_event, { meetingId, kind, title }) => {
    if (
      !["md", "txt", "csv"].includes(kind) ||
      !/^m_[a-f0-9]+$/.test(meetingId)
    )
      throw new Error("导出参数不正确");
    const safeTitle = String(title).replace(/[<>:"/\\|?*\x00-\x1f]/g, "_");
    const result = await dialog.showSaveDialog(mainWindow, {
      defaultPath: `${safeTitle}.${kind}`,
      filters: [{ name: kind.toUpperCase(), extensions: [kind] }],
    });
    if (result.canceled) return false;
    const response = await fetch(
      `${runtime.baseUrl}/api/meetings/${meetingId}/export/${kind}`,
      { headers: { "x-meeting-token": token } },
    );
    if (!response.ok) throw new Error("导出失败，请确认该会议已有对应内容。");
    fs.writeFileSync(
      result.filePath,
      Buffer.from(await response.arrayBuffer()),
    );
    shell.showItemInFolder(result.filePath);
    return true;
  });
  ipcMain.handle("data:open", () => shell.openPath(dataDirectory));
  ipcMain.handle("models:install", () => {
    if (fs.existsSync(path.join(root, "moss-python", "python.exe")))
      return {
        ok: true,
        message: "完整版已内置本地环境，可检查环境后直接选择 MOSS；若文件损坏，请重新解压完整软件包。",
      };
    const script = path.join(root, "scripts", "setup-models.ps1");
    if (!fs.existsSync(script))
      return { ok: false, message: "请使用项目目录中的“安装本地模型.cmd”。" };
    const log = fs.openSync(path.join(dataDirectory, "model-setup.log"), "a");
    const child = spawn(
      "powershell.exe",
      ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
      {
        cwd: root,
        windowsHide: true,
        detached: true,
        stdio: ["ignore", log, log],
      },
    );
    child.unref();
    return {
      ok: true,
      message:
        "本地模型正在后台准备，进度记录在 model-setup.log；下载完成后刷新检查即可。",
    };
  });
}

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on("second-instance", () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
  app
    .whenReady()
    .then(async () => {
      session.defaultSession.setPermissionRequestHandler(
        (contents, permission, callback) => {
          const trusted = [mainWindow, recorderWindow, compactWindow].some(
            (win) =>
              win && !win.isDestroyed() && win.webContents.id === contents.id,
          );
          callback(
            trusted && ["media", "display-capture"].includes(permission),
          );
        },
      );
      session.defaultSession.setDisplayMediaRequestHandler(
        async (_request, callback) => {
          try {
            const sources = await desktopCapturer.getSources({
              types: ["screen"],
              thumbnailSize: { width: 0, height: 0 },
            });
            callback(
              sources.length ? { video: sources[0], audio: "loopback" } : {},
            );
          } catch {
            callback({});
          }
        },
      );
      await startBackend();
      registerIPC();
      recorderWindow = createWindow({ show: false, width: 400, height: 300 });
      await load(recorderWindow, "recorder.html");
      mainWindow = createWindow();
      mainWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
      await load(mainWindow);
      mainWindow.on("close", (event) => {
        if (!app.quitting && recordingState.active) {
          event.preventDefault();
          if (compactWindow) {
            mainWindow.hide();
            compactWindow.show();
          } else mainWindow.minimize();
        }
      });
      mainWindow.on("closed", () => {
        if (!recordingState.active) app.quit();
      });
      if (smoke) {
        const runSmoke = require(
          path.join(
            root,
            "scripts",
            process.env.MEETING_SMOKE_ENGINE === "moss"
              ? "electron-moss-caption-smoke.cjs"
              : "electron-smoke.cjs",
          ),
        );
        await runSmoke({
          win: mainWindow,
          runtime,
          app,
          getState: () => recordingState,
          getCompact: () => compactWindow,
        });
      } else mainWindow.show();
    })
    .catch(async (error) => {
      if (smoke) {
        fs.writeFileSync(
          path.join(root, "artifacts", "desktop-error.txt"),
          String(error.stack),
        );
        app.quitting = true;
        await stopBackend();
        app.exit(1);
      } else {
        dialog.showErrorBox("听会启动失败", String(error.message));
        app.quit();
      }
    });
}
async function stopBackend() {
  try {
    if (runtime && backend)
      await fetch(runtime.baseUrl + "/api/shutdown", {
        method: "POST",
        headers: { "x-meeting-token": token },
        signal: AbortSignal.timeout(20000),
      });
  } catch {
  } finally {
    if (backend) backend.kill();
  }
}
app.on("before-quit", (event) => {
  if (app.quitting) return;
  event.preventDefault();
  app.quitting = true;
  (async () => {
    await stopBackend();
    app.quit();
  })();
});
app.on("window-all-closed", () => app.quit());
