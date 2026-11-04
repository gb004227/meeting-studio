import { useEffect, useRef, useState } from "react";
import {
  AudioLines,
  LayoutDashboard,
  Files,
  CheckSquare,
  Settings as SettingsIcon,
  Plus,
  Mic,
  Upload,
  ArrowUpRight,
  ArrowRight,
  Clock3,
  Users,
  Search,
  ChevronRight,
  Cloud,
  HardDrive,
  ShieldCheck,
  FileText,
  Check,
  Loader2,
  Headphones,
  X,
  Square,
  Pause,
  Play,
  Maximize2,
  Trash2,
  CalendarDays,
} from "lucide-react";
import type { Meeting, RecordingState, ActionItem, Runtime } from "./types";
import { initialize, api } from "./api";
import { RecordingSession } from "./recording";
import { Logo, Modal, Field, Empty, Status, Wave, duration, when } from "./ui";
import Settings from "./Settings";
import MeetingDetail from "./MeetingDetail";

type GlobalAction = ActionItem & {
  meeting_id: string;
  meeting_title: string;
  owner_name: string;
};
const initialRecording: RecordingState = {
  active: false,
  paused: false,
  elapsed: 0,
  level: 0,
};
const modes = [
  {
    id: "realtime",
    title: "实时录音",
    description: "边录边转，专注当下的讨论。",
    icon: Mic,
  },
  {
    id: "file",
    title: "导入录音",
    description: "让已有音频，成为有条理的记录。",
    icon: Upload,
  },
] as const;

export default function App() {
  const [ready, setReady] = useState(false),
    [startupError, setStartupError] = useState(""),
    [page, setPage] = useState("home"),
    [selected, setSelected] = useState<string | null>(null);
  const [meetings, setMeetings] = useState<Meeting[]>([]),
    [actions, setActions] = useState<GlobalAction[]>([]),
    [settings, setSettings] = useState<Record<string, any>>({});
  const [recording, setRecording] = useState<RecordingState>(initialRecording),
    [toastMessage, setToastMessage] = useState(""),
    [search, setSearch] = useState(""),
    [actionFilter, setActionFilter] = useState("open");
  const [newMode, setNewMode] = useState<"realtime" | "file" | null>(null),
    [engine, setEngine] = useState<"doubao" | "moss">(() =>
      localStorage.getItem("lastEngine") === "moss" ? "moss" : "doubao",
    );
  const [title, setTitle] = useState(""),
    [hotwords, setHotwords] = useState(""),
    [source, setSource] = useState<"microphone" | "system" | "both">(
      "microphone",
    ),
    [automatic, setAutomatic] = useState(true),
    [selectedFile, setSelectedFile] = useState<File | string | null>(null),
    [working, setWorking] = useState(false);
  const [completion, setCompletion] = useState<Meeting | null>(null),
    [deleteId, setDeleteId] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null),
    browserRecorder = useRef<RecordingSession | null>(null),
    runtime = useRef<Runtime | null>(null),
    toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null),
    lastSaved = useRef("");
  const compact = location.hash === "#compact";
  function toast(text: string) {
    setToastMessage(text);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToastMessage(""), 6500);
  }
  async function refresh() {
    const [m, a] = await Promise.all([
      api<Meeting[]>("/api/meetings"),
      api<GlobalAction[]>("/api/actions"),
    ]);
    setMeetings(m);
    setActions(a);
  }
  async function refreshSettings() {
    setSettings(await api("/api/settings"));
  }
  function receiveRecording(value: RecordingState) {
    setRecording(value);
    if (value.error) toast(value.error);
    if (
      value.saved &&
      value.meetingId &&
      lastSaved.current !== value.meetingId
    ) {
      lastSaved.current = value.meetingId;
      void api<Meeting>(`/api/meetings/${value.meetingId}`).then(setCompletion);
      void refresh();
    }
  }
  useEffect(() => {
    let disposed = false;
    let off: undefined | (() => void);
    let offError: undefined | (() => void);
    void initialize()
      .then(async (r) => {
        runtime.current = r;
        if (!window.desktop)
          browserRecorder.current = new RecordingSession(r, receiveRecording);
        await Promise.all([refresh(), refreshSettings()]);
        if (disposed) return;
        setReady(true);
        if (window.desktop) {
          receiveRecording(await window.desktop.getRecording());
          off = window.desktop.onRecordingState(receiveRecording);
          offError = window.desktop.onBackendError(toast);
        }
      })
      .catch((error) => setStartupError(error.message));
    const timer = setInterval(() => {
      if (!disposed) void refresh().catch(() => {});
    }, 4000);
    return () => {
      disposed = true;
      clearInterval(timer);
      off?.();
      offError?.();
    };
  }, []);
  useEffect(() => {
    if (!completion) return;
    const timer = setInterval(
      () =>
        void api<Meeting>(`/api/meetings/${completion.id}`)
          .then(setCompletion)
          .catch(() => {}),
      2000,
    );
    return () => clearInterval(timer);
  }, [completion?.id]);
  function navigate(next: string) {
    setPage(next);
    setSelected(null);
    setSearch("");
  }
  function openNew(mode: "realtime" | "file") {
    if (recording.active) {
      toast("当前已有录音进行中，请先结束当前会议。");
      setSelected(recording.meetingId || null);
      return;
    }
    setNewMode(mode);
    setTitle("");
    setHotwords("");
    setSelectedFile(null);
  }
  async function pickFile() {
    if (window.desktop) {
      const file = await window.desktop.pickFile();
      if (file) setSelectedFile(file);
    } else input.current?.click();
  }
  async function create() {
    if (!newMode) return;
    if (newMode === "file" && !selectedFile) return;
    setWorking(true);
    try {
      const fileName =
        typeof selectedFile === "string"
          ? selectedFile.split(/[\\/]/).pop()!
          : selectedFile?.name;
      const meeting = await api<Meeting>("/api/meetings", "POST", {
        title:
          title.trim() ||
          (newMode === "file" && fileName
            ? fileName.replace(/\.[^.]+$/, "")
            : `${new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric" }).format(new Date())}的会议`),
        mode: newMode,
        engine,
        hotwords,
        auto_minutes: automatic,
      });
      setSelected(meeting.id);
      setPage("meetings");
      localStorage.setItem("lastEngine", engine);
      if (newMode === "file") {
        if (typeof selectedFile === "string")
          await api(`/api/meetings/${meeting.id}/file-path`, "POST", {
            path: selectedFile,
          });
        else {
          const body = new FormData();
          body.append("file", selectedFile!);
          await api(`/api/meetings/${meeting.id}/file`, "POST", body);
        }
        toast("文件已导入，转写将在后台继续。");
      } else if (window.desktop) {
        await window.desktop.recordingCommand({
          type: "start",
          meetingId: meeting.id,
          source,
        });
      } else await browserRecorder.current!.start(meeting.id, source);
      setNewMode(null);
      await refresh();
    } catch (error) {
      toast((error as Error).message);
    } finally {
      setWorking(false);
    }
  }
  function command(type: "pause" | "resume" | "stop") {
    if (window.desktop)
      void window.desktop
        .recordingCommand({ type })
        .catch((e) => toast(e.message));
    else if (type === "stop") void browserRecorder.current?.stop();
    else if (type === "pause") browserRecorder.current?.pause();
    else browserRecorder.current?.resume();
  }
  async function deleteMeeting() {
    if (!deleteId) return;
    setWorking(true);
    try {
      await api(`/api/meetings/${deleteId}`, "DELETE");
      setDeleteId(null);
      if (selected === deleteId) setSelected(null);
      await refresh();
      toast("会议及关联的本机记录已删除。");
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setWorking(false);
    }
  }
  async function toggleAction(item: GlobalAction) {
    try {
      await api(
        `/api/meetings/${item.meeting_id}/actions/${item.id}`,
        "PATCH",
        { status: item.status === "done" ? "open" : "done" },
      );
      await refresh();
    } catch (e) {
      toast((e as Error).message);
    }
  }
  if (compact)
    return (
      <div className="compact-shell">
        <span className="compact-drag">
          <span className={recording.paused ? "paused-dot" : "record-dot"} />
          <b>{duration(recording.elapsed)}</b>
        </span>
        <div className="compact-wave">
          <Wave level={recording.level} paused={recording.paused} />
        </div>
        <button
          aria-label={recording.paused ? "继续录音" : "暂停录音"}
          disabled={recording.saving}
          onClick={() => command(recording.paused ? "resume" : "pause")}
        >
          {recording.paused ? <Play size={15} /> : <Pause size={15} />}
        </button>
        <button
          className="compact-stop"
          aria-label="结束录音"
          disabled={recording.saving}
          onClick={() => command("stop")}
        >
          {recording.saving ? (
            <Loader2 size={14} className="spin" />
          ) : (
            <Square size={12} fill="currentColor" />
          )}
        </button>
        <button
          aria-label="展开录音窗口"
          onClick={() => window.desktop?.expand()}
        >
          <Maximize2 size={14} />
        </button>
      </div>
    );
  if (startupError)
    return (
      <div className="startup">
        <Logo />
        <h2>暂时无法连接本地服务</h2>
        <p>{startupError}</p>
        <button className="button primary" onClick={() => location.reload()}>
          <RefreshIcon />
          重试连接
        </button>
      </div>
    );
  if (!ready)
    return (
      <div className="startup">
        <Logo />
        <Loader2 className="spin" />
        <p>正在准备你的会议工作台</p>
      </div>
    );
  const shownMeetings = meetings.filter(
    (m) => !search || m.title.includes(search),
  );
  const meetingTable = (rows: Meeting[], empty = true) => (
    <div className="meeting-table">
      {rows.length ? (
        <>
          <div className="table-head">
            <span>会议名称</span>
            <span>录音时长</span>
            <span>处理状态</span>
            <span />
          </div>
          {rows.map((m) => (
            <div className="meeting-row" key={m.id}>
              <button
                className="meeting-row-main"
                onClick={() => {
                  setSelected(m.id);
                  setPage("meetings");
                }}
              >
                <span
                  className={`meeting-file-icon ${m.mode === "file" ? "file" : ""}`}
                >
                  {m.mode === "realtime" ? (
                    <AudioLines size={22} />
                  ) : (
                    <FileText size={21} />
                  )}
                </span>
                <span>
                  <strong>{m.title}</strong>
                  <small>
                    {when(m.created_at)}
                    <i>·</i>
                    {m.engine === "moss" ? "本地 MOSS" : "豆包云端"}
                  </small>
                </span>
              </button>
              <span className="duration-cell">{duration(m.duration_ms)}</span>
              <Status status={m.status} />
              <div className="table-row-actions">
                <button
                  className="icon-button delete"
                  title="删除会议"
                  onClick={() => setDeleteId(m.id)}
                >
                  <Trash2 size={15} />
                </button>
                <button
                  className="icon-button"
                  title="打开会议"
                  onClick={() => {
                    setSelected(m.id);
                    setPage("meetings");
                  }}
                >
                  <ChevronRight size={19} />
                </button>
              </div>
            </div>
          ))}
        </>
      ) : (
        empty && (
          <Empty
            icon={<Headphones size={30} />}
            title="第一场会议，从这里开始"
            description="开始实时录音，或导入已有录音。文字、纪要与行动项会一起保存在这里。"
          >
            <button
              className="button secondary small"
              onClick={() => openNew("realtime")}
            >
              <Plus size={15} />
              新建会议
            </button>
          </Empty>
        )
      )}
    </div>
  );
  const currentOpen = actions.filter((a) => a.status !== "done");
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Logo />
        <button
          className="button primary sidebar-create"
          onClick={() => openNew("realtime")}
        >
          <Plus size={18} />
          新建录音
        </button>
        <div className="nav-label">我的空间</div>
        <nav>
          {[
            { id: "home", label: "工作台", icon: LayoutDashboard },
            { id: "meetings", label: "会议记录", icon: Files },
            { id: "actions", label: "行动项", icon: CheckSquare },
          ].map((item) => (
            <button
              key={item.id}
              className={page === item.id ? "active" : ""}
              onClick={() => navigate(item.id)}
            >
              <item.icon size={19} />
              {item.label}
              {item.id === "actions" && currentOpen.length > 0 && (
                <span>{currentOpen.length}</span>
              )}
            </button>
          ))}
        </nav>
        {recording.active && (
          <button
            className="sidebar-live"
            onClick={() => {
              setSelected(recording.meetingId || null);
              setPage("meetings");
            }}
          >
            <span className="record-dot" />
            <span>
              会议录音进行中<small>{duration(recording.elapsed)}</small>
            </span>
            <ChevronRight size={15} />
          </button>
        )}
        <div className="sidebar-bottom">
          <button
            className={page === "settings" ? "active" : ""}
            onClick={() => navigate("settings")}
          >
            <SettingsIcon size={19} />
            设置
          </button>
          <div className="storage-indicator">
            <span className="storage-lock">
              <ShieldCheck size={18} />
            </span>
            <div>
              本机会议空间<small>记录由你掌握</small>
            </div>
            <span className="online-dot" />
          </div>
          <p className="sidebar-version">
            听会 0.1.2 <span>WINDOWS</span>
          </p>
        </div>
      </aside>
      <main className="main-area">
        {selected ? (
          <MeetingDetail
            key={selected}
            id={selected}
            onBack={() => navigate("meetings")}
            toast={toast}
            recording={recording}
            onRecordCommand={command}
            onCompact={() => {
              void window.desktop?.compact();
            }}
            onChanged={() => void refresh()}
          />
        ) : page === "settings" ? (
          <Settings toast={toast} onSaved={() => void refreshSettings()} />
        ) : page === "actions" ? (
          <div className="page">
            <div className="page-heading">
              <div>
                <div className="eyebrow">FOLLOW THROUGH</div>
                <h1>行动项</h1>
                <p>让讨论有后续，让进展看得见。</p>
              </div>
              <div className="segmented small-segment">
                {[
                  ["open", "待完成"],
                  ["all", "全部"],
                  ["done", "已完成"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    className={actionFilter === value ? "active" : ""}
                    onClick={() => setActionFilter(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="global-actions">
              {actions.filter(
                (a) =>
                  actionFilter === "all" ||
                  (actionFilter === "done"
                    ? a.status === "done"
                    : a.status !== "done"),
              ).length ? (
                actions
                  .filter(
                    (a) =>
                      actionFilter === "all" ||
                      (actionFilter === "done"
                        ? a.status === "done"
                        : a.status !== "done"),
                  )
                  .map((item) => (
                    <div
                      className={`global-action-row ${item.status === "done" ? "done" : ""}`}
                      key={item.id}
                    >
                      <button
                        className="task-checkbox"
                        aria-label="切换任务完成状态"
                        onClick={() => toggleAction(item)}
                      >
                        {item.status === "done" && <Check size={14} />}
                      </button>
                      <div>
                        <p>{item.task}</p>
                        <button
                          className="action-source"
                          onClick={() => {
                            setSelected(item.meeting_id);
                            setPage("meetings");
                          }}
                        >
                          <FileText size={13} />
                          {item.meeting_title}
                          <ArrowUpRight size={12} />
                        </button>
                      </div>
                      <span>
                        <Users size={14} />
                        {item.owner_name || "负责人未明确"}
                      </span>
                      <span>
                        <CalendarDays size={14} />
                        {item.due_date || "日期未明确"}
                      </span>
                    </div>
                  ))
              ) : (
                <Empty
                  icon={<CheckSquare size={32} />}
                  title="事情都在掌握之中"
                  description="会议中明确的任务会在生成纪要后汇总到这里，支持负责人、日期与完成状态管理。"
                />
              )}
            </div>
          </div>
        ) : page === "meetings" ? (
          <div className="page">
            <div className="page-heading">
              <div>
                <div className="eyebrow">YOUR MEETINGS</div>
                <h1>
                  会议记录{" "}
                  <span className="heading-count">{meetings.length}</span>
                </h1>
                <p>每一次讨论，都值得被好好记住。</p>
              </div>
              <button
                className="button primary"
                onClick={() => openNew("realtime")}
              >
                <Plus size={17} />
                新建录音
              </button>
            </div>
            <div className="list-toolbar">
              <div className="search-field">
                <Search size={16} />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="搜索会议标题"
                />
              </div>
              <button
                className="button secondary small"
                onClick={() => openNew("file")}
              >
                <Upload size={15} />
                导入录音
              </button>
            </div>
            <section className="panel">{meetingTable(shownMeetings)}</section>
          </div>
        ) : (
          <div className="page dashboard">
            <div className="dashboard-topline">
              <span>我的工作台</span>
              <span>
                {new Intl.DateTimeFormat("zh-CN", {
                  month: "long",
                  day: "numeric",
                  weekday: "long",
                }).format(new Date())}
              </span>
            </div>
            <div className="hero">
              <div className="eyebrow">
                <span className="online-dot" /> LISTEN. REMEMBER. ACT.
              </div>
              <h1>把讨论，变成清晰的行动。</h1>
              <p>专注交流，让听会帮你记住每一个重要瞬间。</p>
              <span className="hero-watermark">
                <AudioLines size={155} strokeWidth={0.8} />
              </span>
            </div>
            <div className="mode-grid">
              {modes.map((mode) => (
                <button
                  className={`mode-card mode-${mode.id}`}
                  key={mode.id}
                  onClick={() => openNew(mode.id)}
                  onDragOver={(e) => {
                    if (mode.id === "file") e.preventDefault();
                  }}
                  onDrop={(e) => {
                    e.preventDefault();
                    if (e.dataTransfer.files[0]) {
                      setSelectedFile(e.dataTransfer.files[0]);
                      setNewMode("file");
                    }
                  }}
                >
                  <div className="mode-card-top">
                    <span className="mode-icon">
                      <mode.icon size={25} />
                    </span>
                    <ArrowUpRight size={22} />
                  </div>
                  <h2>{mode.title}</h2>
                  <p>{mode.description}</p>
                  <div className="mode-footer">
                    <span>
                      {mode.id === "realtime"
                        ? "麦克风 · 电脑声音 · 实时字幕"
                        : "音频 / 视频 · 时间戳 · 说话人"}
                    </span>
                    <ArrowRight size={17} />
                  </div>
                </button>
              ))}
            </div>
            <div className="feature-strip">
              <span>
                <Check size={14} />
                会议纪要
              </span>
              <span>
                <Check size={14} />
                说话人实时改名
              </span>
              <span>
                <Check size={14} />
                行动项与原文回溯
              </span>
              <span className="feature-engines">
                <Cloud size={14} />
                豆包云端<i>/</i>
                <HardDrive size={14} />
                MOSS 本地，自由选择
              </span>
            </div>
            <div className="stats-grid">
              <div>
                <span className="stat-icon">
                  <Files size={19} />
                </span>
                <div>
                  <span>已记录会议</span>
                  <strong>
                    {meetings.length}
                    <small>场</small>
                  </strong>
                </div>
              </div>
              <div>
                <span className="stat-icon">
                  <Clock3 size={19} />
                </span>
                <div>
                  <span>累计录音</span>
                  <strong>
                    {(
                      meetings.reduce((sum, m) => sum + m.duration_ms, 0) /
                      3600000
                    ).toFixed(1)}
                    <small>小时</small>
                  </strong>
                </div>
              </div>
              <div>
                <span className="stat-icon">
                  <CheckSquare size={19} />
                </span>
                <div>
                  <span>待完成行动项</span>
                  <strong>
                    {currentOpen.length}
                    <small>项</small>
                  </strong>
                </div>
              </div>
            </div>
            <div className="section-header">
              <div>
                <h2>最近会议</h2>
                <span>声音留下，思路继续。</span>
              </div>
              <button
                className="text-button"
                onClick={() => navigate("meetings")}
              >
                查看全部
                <ArrowRight size={15} />
              </button>
            </div>
            <section className="panel">
              {meetingTable(meetings.slice(0, 5))}
            </section>
            <div className="dashboard-footnote">
              <ShieldCheck size={14} />
              本机保存录音与记录，按需选择云端处理。
              <button onClick={() => navigate("settings")}>
                管理模型与数据设置
                <ArrowUpRight size={12} />
              </button>
            </div>
          </div>
        )}
      </main>
      {newMode && (
        <Modal
          title={newMode === "realtime" ? "开始一场新的讨论" : "导入会议录音"}
          subtitle={
            newMode === "realtime"
              ? "选好录音来源与引擎，余下交给听会。"
              : "支持常见音频与视频文件，原始文件会保留。"
          }
          onClose={() => {
            if (!working) setNewMode(null);
          }}
          wide
        >
          <div className="segmented">
            {modes.map((mode) => (
              <button
                key={mode.id}
                className={newMode === mode.id ? "active" : ""}
                disabled={working}
                onClick={() => setNewMode(mode.id)}
              >
                <mode.icon size={16} />
                {mode.title}
              </button>
            ))}
          </div>
          <Field label="会议标题">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="例如：产品周会、客户沟通、项目复盘"
              maxLength={200}
            />
          </Field>
          <Field label="转写引擎">
            <div className="engine-choices">
              <button
                className={engine === "doubao" ? "selected" : ""}
                onClick={() => setEngine("doubao")}
              >
                <Cloud size={21} />
                <span>
                  <strong>豆包云端</strong>
                  <small>实时识别 · 音频发送至云端</small>
                </span>
                {engine === "doubao" && <Check size={16} />}
              </button>
              <button
                className={engine === "moss" ? "selected" : ""}
                onClick={() => setEngine("moss")}
              >
                <HardDrive size={21} />
                <span>
                  <strong>MOSS 本地</strong>
                  <small>
                    {settings.moss_ready
                      ? settings.local_live_ready
                        ? "本地流式字幕 · MOSS 精修"
                        : "本地分段预览 · 音频留在本机"
                      : "首次使用需准备本地模型"}
                  </small>
                </span>
                {engine === "moss" && <Check size={16} />}
              </button>
            </div>
          </Field>
          {newMode === "realtime" ? (
            <Field label="录音来源">
              <select
                value={source}
                onChange={(e) => setSource(e.target.value as typeof source)}
              >
                <option value="microphone">
                  仅麦克风 · 线下会议 / 个人语音
                </option>
                <option value="both">
                  麦克风 + 电脑声音 · 线上会议（含耳机）
                </option>
                <option value="system">仅电脑声音 · 播放内容</option>
              </select>
            </Field>
          ) : (
            <div
              className={`upload-zone ${selectedFile ? "has-file" : ""}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (e.dataTransfer.files[0])
                  setSelectedFile(e.dataTransfer.files[0]);
              }}
              onClick={() => void pickFile()}
            >
              <Upload size={27} />
              <strong>
                {selectedFile
                  ? typeof selectedFile === "string"
                    ? selectedFile.split(/[\\/]/).pop()
                    : selectedFile.name
                  : "选择文件，或将录音拖到这里"}
              </strong>
              <span>
                {selectedFile
                  ? "点击可重新选择"
                  : "WAV、MP3、M4A、FLAC、MP4 等常见格式"}
              </span>
            </div>
          )}
          <Field
            label="会议热词（可选）"
            hint={
              engine === "moss"
                ? "首版本地模式使用标准转写提示，热词仅用于豆包云端。"
                : "用逗号分隔人名、项目和专业词，有助于识别拼写。"
            }
          >
            <input
              value={hotwords}
              onChange={(e) => setHotwords(e.target.value)}
              placeholder="张三，产品名称，项目代号"
            />
          </Field>
          <label className="check-option">
            <input
              type="checkbox"
              checked={automatic}
              onChange={(e) => setAutomatic(e.target.checked)}
            />
            <span>
              转写完成后自动生成纪要和行动项
              <small>
                {settings.secrets?.llm_api_key
                  ? "使用已配置的文本模型 API，转写文字会发送至该服务。"
                  : "当前使用基础原文提取，可在设置中接入 AI 纪要模型。"}
              </small>
            </span>
          </label>
          {engine === "moss" && newMode === "realtime" && (
            <div className="notice quiet">
              <Clock3 size={17} />
              MOSS 使用本地分段准实时，CPU
              可能较慢；录音持续保存，结束后完整精修。
            </div>
          )}
          <div className="modal-footer">
            <button
              className="button secondary"
              disabled={working}
              onClick={() => setNewMode(null)}
            >
              取消
            </button>
            <button
              className="button primary"
              onClick={() => void create()}
              disabled={working || (newMode === "file" && !selectedFile)}
            >
              {working ? (
                <Loader2 size={17} className="spin" />
              ) : newMode === "realtime" ? (
                <Mic size={17} />
              ) : (
                <Upload size={17} />
              )}{" "}
              {working
                ? "正在准备"
                : newMode === "realtime"
                  ? "开始录音"
                  : "导入并转写"}
            </button>
          </div>
          <input
            type="file"
            hidden
            ref={input}
            accept="audio/*,video/*,.m4a,.flac,.amr"
            onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
          />
        </Modal>
      )}
      {completion && (
        <Modal
          title="这场讨论，已为你留下记录"
          subtitle="录音已保存，转写与纪要任务会在后台继续。"
          onClose={() => setCompletion(null)}
        >
          <div className="completion-icon">
            <Check size={28} />
          </div>
          <div className="completion-stats">
            <div>
              <span>录音时长</span>
              <strong>{duration(completion.duration_ms)}</strong>
            </div>
            <div>
              <span>纪要</span>
              <strong>
                {completion.minutes
                  ? completion.minutes.data.summary.join("").length + " 字"
                  : "—"}
              </strong>
            </div>
            <div>
              <span>文字记录</span>
              <strong>
                {completion.segments.length
                  ? completion.segments.reduce(
                      (sum, s) => sum + s.text.length,
                      0,
                    ) + " 字"
                  : "—"}
              </strong>
            </div>
          </div>
          <div className="modal-footer">
            <button
              className="button secondary"
              onClick={() => setCompletion(null)}
            >
              稍后查看
            </button>
            <button
              className="button primary"
              onClick={() => {
                setSelected(completion.id);
                setPage("meetings");
                setCompletion(null);
              }}
            >
              查看会议
              <ArrowRight size={16} />
            </button>
          </div>
        </Modal>
      )}
      {deleteId && (
        <Modal
          title="删除这场会议？"
          subtitle="将删除本机录音、文字、纪要和行动项。已导出的文件保留。"
          onClose={() => setDeleteId(null)}
        >
          <div className="modal-footer">
            <button
              className="button secondary"
              onClick={() => setDeleteId(null)}
            >
              取消
            </button>
            <button
              className="button danger"
              disabled={working}
              onClick={() => void deleteMeeting()}
            >
              {working ? (
                <Loader2 size={15} className="spin" />
              ) : (
                <Trash2 size={15} />
              )}
              删除会议
            </button>
          </div>
        </Modal>
      )}
      {toastMessage && (
        <div className="toast" role="status">
          <span>{toastMessage}</span>
          <button aria-label="关闭提示" onClick={() => setToastMessage("")}>
            <X size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
function RefreshIcon() {
  return <Loader2 size={16} />;
}
