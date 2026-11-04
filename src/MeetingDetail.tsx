import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  AudioLines,
  FileText,
  Users,
  Clock3,
  Download,
  RefreshCw,
  CheckSquare,
  Play,
  Pause,
  Mic,
  Minimize2,
  Square,
  Loader2,
  Search,
  Pencil,
  Check,
  ChevronDown,
  Link2,
  AlertCircle,
  Merge,
} from "lucide-react";
import type { Meeting, RecordingState, ActionItem } from "./types";
import { api, asset, wsUrl } from "./api";
import {
  duration,
  when,
  Status,
  Engine,
  Empty,
  Modal,
  Field,
  Wave,
} from "./ui";

const colors = [
  "#129b88",
  "#4878cb",
  "#b079bd",
  "#d1963b",
  "#c86366",
  "#5995a3",
];
export default function MeetingDetail({
  id,
  onBack,
  toast,
  recording,
  onRecordCommand,
  onCompact,
  onChanged,
}: {
  id: string;
  onBack: () => void;
  toast: (text: string) => void;
  recording: RecordingState;
  onRecordCommand: (type: "pause" | "resume" | "stop") => void;
  onCompact: () => void;
  onChanged: () => void;
}) {
  const [meeting, setMeeting] = useState<Meeting | null>(null),
    [tab, setTab] = useState("transcript"),
    [search, setSearch] = useState(""),
    [filter, setFilter] = useState("");
  const [partial, setPartial] = useState(""),
    [warning, setWarning] = useState(""),
    [loading, setLoading] = useState(""),
    [latency, setLatency] = useState<number | null>(null);
  const [speakerEdit, setSpeakerEdit] = useState<{
      id: string;
      name: string;
    } | null>(null),
    [editName, setEditName] = useState(""),
    [editText, setEditText] = useState<{ id: string; text: string } | null>(
      null,
    ),
    [exportOpen, setExportOpen] = useState(false);
  const [mergeTarget, setMergeTarget] = useState("");
  const [summaryEdit, setSummaryEdit] = useState(false);
  const [summaryDraft, setSummaryDraft] = useState("");
  const [renameTitle, setRenameTitle] = useState(false),
    [title, setTitle] = useState(""),
    [playing, setPlaying] = useState(false),
    [playTime, setPlayTime] = useState(0),
    [reengine, setReengine] = useState<"doubao" | "moss">("doubao");
  const audio = useRef<HTMLAudioElement>(null),
    bottom = useRef<HTMLDivElement>(null);
  const live = recording.active && recording.meetingId === id;
  const refresh = () =>
    api<Meeting>(`/api/meetings/${id}`).then((value) => {
      setMeeting(value);
      return value;
    });
  useEffect(() => {
    let valid = true;
    setMeeting(null);
    setPartial("");
    setWarning("");
    setLatency(null);
    void refresh()
      .then((m) => {
        if (valid) {
          setTitle(m.title);
          setReengine(m.engine);
          setTab(m.minutes && !live ? "minutes" : "transcript");
        }
      })
      .catch((e) => toast(e.message));
    const timer = setInterval(() => {
      if (valid) void refresh().catch(() => {});
    }, 2000);
    const socket = new WebSocket(wsUrl(`/api/meetings/${id}/events`));
    socket.onmessage = (event) => {
      const value = JSON.parse(event.data);
      if (value.type === "saved") setPartial("");
      if (value.type === "warning") setWarning(value.message);
      if (value.type === "transcript") {
        setPartial(value.partial || "");
        if (value.latency != null) setLatency(value.latency);
      }
      if (value.refresh !== false) void refresh().catch(() => {});
    };
    return () => {
      valid = false;
      clearInterval(timer);
      socket.close();
    };
  }, [id]);
  useEffect(() => {
    if (live && tab === "transcript" && !search && !filter)
      bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [meeting?.segments.length, partial]);
  async function run(kind: string) {
    setLoading(kind);
    try {
      await api(
        `/api/meetings/${id}/${kind}`,
        "POST",
        kind === "transcribe" ? { engine: reengine } : {},
      );
      toast(kind === "minutes" ? "纪要任务已开始" : "转写任务已加入队列");
      await refresh();
      onChanged();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setLoading("");
    }
  }
  async function exportFile(kind: string) {
    setExportOpen(false);
    try {
      if (window.desktop)
        await window.desktop.exportFile({
          meetingId: id,
          kind,
          title: meeting!.title,
        });
      else {
        const response = await fetch(
          asset(`/api/meetings/${id}/export/${kind}`),
        );
        if (!response.ok) throw new Error("尚无可导出的内容");
        const url = URL.createObjectURL(await response.blob());
        const a = document.createElement("a");
        a.href = url;
        a.download = `${meeting!.title}.${kind}`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (e) {
      toast((e as Error).message);
    }
  }
  async function saveSpeaker() {
    if (!speakerEdit) return;
    try {
      setMeeting(
        await api(`/api/meetings/${id}/speakers/${speakerEdit.id}`, "PATCH", {
          name: editName,
        }),
      );
      setSpeakerEdit(null);
      toast("姓名已更新，历史和后续关联发言同步显示。");
    } catch (e) {
      toast((e as Error).message);
    }
  }
  function seek(segmentId: string) {
    const segment = meeting?.segments.find((s) => s.id === segmentId);
    if (!segment) {
      toast("依据来自其他转写版本，请切换到纪要来源版本查看。");
      return;
    }
    setTab("transcript");
    if (audio.current) {
      audio.current.currentTime = segment.start_ms / 1000;
      void audio.current.play();
    }
    setTimeout(
      () =>
        document
          .getElementById(segmentId)
          ?.scrollIntoView({ behavior: "smooth", block: "center" }),
      100,
    );
  }
  async function updateAction(
    item: ActionItem,
    values: Record<string, unknown>,
  ) {
    try {
      setMeeting(
        await api(`/api/meetings/${id}/actions/${item.id}`, "PATCH", values),
      );
    } catch (e) {
      toast((e as Error).message);
    }
  }
  if (!meeting)
    return (
      <div className="loading-page">
        <Loader2 className="spin" />
        正在打开会议
      </div>
    );
  const name = (sid?: string | null) =>
    meeting.speakers.find((p) => p.id === sid)?.name || "待确认";
  const activeTask = meeting.tasks.find((t) =>
    ["running", "queued"].includes(t.state),
  );
  const hasAudio = !!meeting.audio_path && meeting.duration_ms > 0;
  const minutes = meeting.minutes?.data;
  const visible = meeting.segments.filter(
    (s) =>
      (!filter || s.speaker_id === filter) &&
      (!search ||
        s.text.includes(search) ||
        name(s.speaker_id).includes(search)),
  );
  return (
    <div className="page detail-page">
      <button className="back-link" onClick={onBack}>
        <ArrowLeft size={16} />
        全部会议
      </button>
      <div className="detail-heading">
        <div>
          <div className="row">
            <h1>{meeting.title}</h1>
            <button
              className="icon-button faint"
              aria-label="修改标题"
              onClick={() => {
                setTitle(meeting.title);
                setRenameTitle(true);
              }}
            >
              <Pencil size={16} />
            </button>
          </div>
          <div className="metadata">
            <span>
              <Clock3 size={14} />
              {when(meeting.created_at)}
            </span>
            <span>
              {duration(live ? recording.elapsed : meeting.duration_ms)}
            </span>
            <span>
              <Users size={14} />
              {meeting.speakers.length} 位说话人
            </span>
            <Engine engine={meeting.engine} />
            <Status status={meeting.status} />
          </div>
        </div>
        <div className="detail-actions">
          {!live && (
            <>
              <select
                className="compact-select"
                value={reengine}
                onChange={(e) =>
                  setReengine(e.target.value as "doubao" | "moss")
                }
                aria-label="重新转写引擎"
              >
                <option value="doubao">豆包云端</option>
                <option value="moss">MOSS 本地</option>
              </select>
              <button
                className="button secondary small"
                onClick={() => run("transcribe")}
                disabled={!!loading || !!activeTask || !hasAudio}
              >
                <RefreshCw size={15} />
                重新转写
              </button>
            </>
          )}
          <div className="dropdown">
            <button
              className="button secondary small"
              onClick={() => setExportOpen(!exportOpen)}
            >
              <Download size={15} />
              导出
              <ChevronDown size={13} />
            </button>
            {exportOpen && (
              <div className="dropdown-menu">
                {[
                  ["md", "会议纪要 · Markdown"],
                  ["txt", "文字记录 · TXT"],
                  ["csv", "行动项 · CSV"],
                ].map(([kind, label]) => (
                  <button key={kind} onClick={() => exportFile(kind)}>
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
      {live && (
        <div className="recording-panel">
          <div className="recording-indicator">
            <span className={recording.paused ? "paused-dot" : "record-dot"} />
            <strong>
              {recording.saving
                ? "正在保存"
                : recording.paused
                  ? "录音已暂停"
                  : "正在录音"}
            </strong>
            <span>{duration(recording.elapsed)}</span>
          </div>
          <Wave level={recording.level} paused={recording.paused} />
          <div className="row">
            <button className="button ghost small" onClick={onCompact}>
              <Minimize2 size={16} />
              收起
            </button>
            <button
              className="button secondary small"
              onClick={() =>
                onRecordCommand(recording.paused ? "resume" : "pause")
              }
              disabled={recording.saving}
            >
              {recording.paused ? <Play size={16} /> : <Pause size={16} />}
            </button>
            <button
              className="button danger small"
              onClick={() => onRecordCommand("stop")}
              disabled={recording.saving}
            >
              {recording.saving ? (
                <Loader2 size={15} className="spin" />
              ) : (
                <Square size={13} fill="currentColor" />
              )}
              结束录音
            </button>
          </div>
        </div>
      )}
      {(meeting.error || warning) && (
        <div className="notice warning">
          <AlertCircle size={18} />
          <span>{meeting.error || warning}</span>
          <button
            className="icon-button"
            onClick={() => setWarning("")}
            aria-label="关闭提示"
          >
            ×
          </button>
        </div>
      )}
      {activeTask && (
        <div className="progress-note">
          <Loader2 size={16} className="spin" />
          {activeTask.stage}
          <span>录音与已有结果已保留</span>
        </div>
      )}
      <div className="detail-layout">
        <section className="content-card">
          <div className="content-tabs">
            <button
              className={tab === "minutes" ? "active" : ""}
              onClick={() => setTab("minutes")}
            >
              <FileText size={17} />
              智能纪要
            </button>
            <button
              className={tab === "transcript" ? "active" : ""}
              onClick={() => setTab("transcript")}
            >
              <AudioLines size={18} />
              文字记录<span>{meeting.segments.length}</span>
            </button>
            <button
              className={tab === "actions" ? "active" : ""}
              onClick={() => setTab("actions")}
            >
              <CheckSquare size={17} />
              行动项<span>{minutes?.action_items.length || 0}</span>
            </button>
          </div>
          {tab === "transcript" && (
            <>
              <div className="transcript-toolbar">
                <div className="search-field">
                  <Search size={15} />
                  <input
                    placeholder="搜索发言或说话人"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  <option value="">全部说话人</option>
                  {meeting.speakers.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                {meeting.versions.length > 1 && (
                  <select
                    aria-label="转写版本"
                    value={meeting.current_version}
                    onChange={async (e) => {
                      try {
                        setMeeting(
                          await api(`/api/meetings/${id}/version`, "POST", {
                            version_id: e.target.value,
                          }),
                        );
                      } catch (error) {
                        toast((error as Error).message);
                      }
                    }}
                  >
                    {meeting.versions.map((v, i) => (
                      <option key={v.id} value={v.id}>
                        {v.kind === "human"
                          ? "人工校对"
                          : v.kind === "live"
                            ? "实时记录"
                            : v.kind === "moss"
                              ? "MOSS 精修"
                              : "豆包转写"}{" "}
                        · 版本 {meeting.versions.length - i}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              {live && (
                <div className="live-caption-info" role="status">
                  <span className="pulse-dot" />
                  <span>
                    {meeting.engine === "moss"
                      ? meeting.caption_engine === "local_stream"
                        ? "本地流式字幕预览：边说边显示，结束后由 MOSS 完整精修；预览文字可能再次校正。"
                        : "MOSS 分段字幕：CPU 识别有延迟，可在设置中准备本地流式字幕组件。"
                      : "实时字幕：识别中的文字会先显示，随后自动校正并补齐说话人。"}
                  </span>
                </div>
              )}
              <div className="transcript-body">
                {!visible.length && !partial ? (
                  <Empty
                    icon={<Mic size={28} />}
                    title={live ? "正在听，文字即将出现" : "还没有文字记录"}
                    description={
                      live
                        ? meeting.engine === "moss"
                          ? meeting.caption_engine === "local_stream"
                            ? "正在本机识别，你说的话会逐步显示在这里。"
                            : "MOSS 正在本机分段识别，CPU 处理可能需要等待。"
                          : "你说的话会在这里逐句显示。"
                        : "选择录音文件并转写，或等待当前任务完成。"
                    }
                  />
                ) : (
                  visible.map((segment) => {
                    const p = meeting.speakers.find(
                      (p) => p.id === segment.speaker_id,
                    );
                    return (
                      <article
                        className={`transcript-segment ${playTime >= segment.start_ms && playTime < segment.end_ms ? "playing" : ""}`}
                        id={segment.id}
                        key={segment.id}
                      >
                        <div className="segment-meta">
                          <span
                            className="avatar"
                            style={{
                              background:
                                colors[(p?.color || 0) % colors.length] + "18",
                              color: colors[(p?.color || 0) % colors.length],
                            }}
                          >
                            {(p?.name || "?").slice(-2)}
                          </span>
                          <button
                            className="speaker-name"
                            onClick={() => {
                              if (p) {
                                setSpeakerEdit(p);
                                setEditName(p.name);
                              }
                            }}
                          >
                            {p?.name || "说话人待确认"}
                            <Pencil size={11} />
                          </button>
                          <button
                            className="segment-time"
                            onClick={() => seek(segment.id)}
                          >
                            {duration(segment.start_ms)}
                          </button>
                          <div className="segment-tools">
                            <select
                              aria-label="修改发言归属"
                              value={segment.speaker_id || ""}
                              onChange={async (e) => {
                                try {
                                  let speakerId = e.target.value || null;
                                  if (speakerId === "__new__") {
                                    const created = await api(
                                      `/api/meetings/${id}/speakers`,
                                      "POST",
                                      { name: "新说话人" },
                                    );
                                    speakerId = created.id;
                                  }
                                  setMeeting(
                                    await api(
                                      `/api/meetings/${id}/segments/${segment.id}`,
                                      "PATCH",
                                      { speaker_id: speakerId },
                                    ),
                                  );
                                } catch (error) {
                                  toast((error as Error).message);
                                }
                              }}
                            >
                              <option value="">待确认</option>
                              <option value="__new__">
                                ＋ 新建说话人（拆分此段）
                              </option>
                              {meeting.speakers.map((p) => (
                                <option key={p.id} value={p.id}>
                                  {p.name}
                                </option>
                              ))}
                            </select>
                            <button
                              className="icon-button"
                              title="校对这句话"
                              onClick={() =>
                                setEditText({
                                  id: segment.id,
                                  text: segment.text,
                                })
                              }
                            >
                              <Pencil size={14} />
                            </button>
                          </div>
                        </div>
                        {editText?.id === segment.id ? (
                          <div className="segment-editor">
                            <textarea
                              value={editText.text}
                              onChange={(e) =>
                                setEditText({
                                  ...editText,
                                  text: e.target.value,
                                })
                              }
                            />
                            <div className="row">
                              <button
                                className="button primary small"
                                onClick={async () => {
                                  try {
                                    setMeeting(
                                      await api(
                                        `/api/meetings/${id}/segments/${segment.id}`,
                                        "PATCH",
                                        { text: editText.text },
                                      ),
                                    );
                                    setEditText(null);
                                  } catch (e) {
                                    toast((e as Error).message);
                                  }
                                }}
                              >
                                <Check size={14} />
                                保存校对
                              </button>
                              <button
                                className="button ghost small"
                                onClick={() => setEditText(null)}
                              >
                                取消
                              </button>
                            </div>
                          </div>
                        ) : (
                          <p onClick={() => seek(segment.id)}>{segment.text}</p>
                        )}
                        {!!segment.edited && (
                          <span className="edited-label">已人工校对</span>
                        )}
                      </article>
                    );
                  })
                )}
                {partial && (
                  <article className="transcript-segment provisional">
                    <div className="segment-meta">
                      <span className="pulse-dot" />
                      正在识别
                      {latency != null && (
                        <span className="muted">延迟约 {latency} 秒</span>
                      )}
                    </div>
                    <p>
                      {partial}
                      <span className="typing-cursor" />
                    </p>
                  </article>
                )}
                <div ref={bottom} />
              </div>
            </>
          )}
          {tab === "minutes" &&
            (minutes ? (
              <div className="minutes-body">
                {meeting.minutes?.stale && (
                  <div className="notice warning">
                    <RefreshCw size={16} />
                    原文已更新，此纪要保留原版本依据。可重新生成。
                  </div>
                )}
                {minutes.notice && (
                  <div className="notice quiet">
                    <FileText size={17} />
                    {minutes.notice}
                  </div>
                )}
                <div className="minutes-section-heading">
                  <span className="eyebrow">MEETING BRIEF</span>
                  <button
                    className="button ghost small"
                    disabled={!!loading || !!activeTask || live}
                    onClick={() => run("minutes")}
                  >
                    <RefreshCw size={14} />
                    重新生成
                  </button>
                </div>
                <div className="row between">
                  <h2>会议总结</h2>
                  <button
                    className="button ghost small"
                    onClick={() => {
                      setSummaryDraft(minutes.summary.join("\n"));
                      setSummaryEdit(true);
                    }}
                  >
                    <Pencil size={13} />
                    编辑总结
                  </button>
                </div>
                <ul className="summary-list">
                  {minutes.summary.map((s, i) => (
                    <li key={i}>
                      <span>{String(i + 1).padStart(2, "0")}</span>
                      <p>{s}</p>
                    </li>
                  ))}
                </ul>
                {minutes.topics?.map((topic, i) => (
                  <section className="topic-card" key={i}>
                    <h3>{topic.title}</h3>
                    <ul>
                      {topic.points.map((p, j) => (
                        <li key={j}>{p}</li>
                      ))}
                    </ul>
                  </section>
                ))}
                <h2 className="subheading">明确决策</h2>
                {minutes.decisions.length ? (
                  minutes.decisions.map((d) => (
                    <div className="decision" key={d.id}>
                      <CheckCircle />
                      <p>{d.text}</p>
                      <button
                        className="evidence"
                        onClick={() => seek(d.evidence_segment_ids[0])}
                      >
                        <Link2 size={13} />
                        原文依据
                      </button>
                    </div>
                  ))
                ) : (
                  <p className="muted">原文中暂未提取到明确决策。</p>
                )}
                {minutes.pending_questions?.length > 0 && (
                  <>
                    <h2 className="subheading">待确认问题</h2>
                    <ul>
                      {minutes.pending_questions.map((p, i) => (
                        <li key={i}>{p}</li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            ) : (
              <Empty
                icon={<FileText size={30} />}
                title={activeTask ? "纪要正在准备中" : "把发言整理成清晰结论"}
                description={
                  live
                    ? "结束录音后自动生成纪要与行动项。"
                    : meeting.segments.length
                      ? "根据现有文字生成总结、决策和行动项，每一项都能回到原文。"
                      : "完成转写后，这里将展示会议总结。"
                }
              >
                {!live && meeting.segments.length > 0 && (
                  <button
                    className="button primary"
                    disabled={!!activeTask || !!loading}
                    onClick={() => run("minutes")}
                  >
                    <FileText size={16} />
                    生成会议纪要
                  </button>
                )}
              </Empty>
            ))}
          {tab === "actions" && (
            <div className="actions-body">
              <div className="minutes-section-heading">
                <div>
                  <h2>让每一件事有着落</h2>
                  <p className="muted">
                    {minutes?.action_items.filter((a) => a.status === "done")
                      .length || 0}{" "}
                    项已完成，共 {minutes?.action_items.length || 0} 项
                  </p>
                </div>
                <button
                  className="button secondary small"
                  onClick={() => exportFile("csv")}
                >
                  <Download size={15} />
                  导出清单
                </button>
              </div>
              {minutes?.action_items.length ? (
                minutes.action_items.map((item) => (
                  <div
                    className={`action-card ${item.status === "done" ? "done" : ""}`}
                    key={item.id}
                  >
                    <button
                      className="task-checkbox"
                      aria-label={
                        item.status === "done" ? "标为未完成" : "标为已完成"
                      }
                      onClick={() =>
                        updateAction(item, {
                          status: item.status === "done" ? "open" : "done",
                        })
                      }
                    >
                      {item.status === "done" && <Check size={14} />}
                    </button>
                    <div className="action-content">
                      <p
                        contentEditable
                        suppressContentEditableWarning
                        onBlur={(e) => {
                          if (e.currentTarget.textContent !== item.task)
                            void updateAction(item, {
                              task: e.currentTarget.textContent || item.task,
                            });
                        }}
                      >
                        {item.task}
                      </p>
                      <div className="action-fields">
                        <label>
                          <Users size={13} />
                          <select
                            value={item.owner_speaker_id || ""}
                            onChange={(e) =>
                              updateAction(item, {
                                owner_speaker_id: e.target.value || null,
                              })
                            }
                          >
                            <option value="">
                              {item.owner_mentioned_as || "负责人未明确"}
                            </option>
                            {meeting.speakers.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          <Clock3 size={13} />
                          <input
                            type="date"
                            aria-label="截止日期"
                            value={item.due_date || ""}
                            onChange={(e) =>
                              updateAction(item, {
                                due_date: e.target.value || null,
                              })
                            }
                          />
                        </label>
                        <button
                          className="evidence"
                          onClick={() => seek(item.evidence_segment_ids[0])}
                        >
                          <Link2 size={13} />
                          原文依据
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <Empty
                  icon={<CheckSquare size={28} />}
                  title="暂无明确行动项"
                  description="明确的任务、负责人和截止时间会在生成纪要后展示，原文未说明的信息保留为未明确。"
                />
              )}
            </div>
          )}
        </section>
        <aside className="meeting-aside">
          <div className="aside-card">
            <div className="row between">
              <h3>会议说话人</h3>
              <span className="count">{meeting.speakers.length}</span>
            </div>
            <p className="aside-hint">点击姓名修改，关联发言同步更新。</p>
            {meeting.speakers.length ? (
              meeting.speakers.map((p) => (
                <button
                  className="person-row"
                  key={p.id}
                  onClick={() => {
                    setSpeakerEdit(p);
                    setEditName(p.name);
                  }}
                >
                  <span
                    className="avatar"
                    style={{
                      background: colors[p.color % colors.length] + "18",
                      color: colors[p.color % colors.length],
                    }}
                  >
                    {p.name.slice(-2)}
                  </span>
                  <span>
                    {p.name}
                    <small>
                      {
                        meeting.segments.filter((s) => s.speaker_id === p.id)
                          .length
                      }{" "}
                      段发言
                    </small>
                  </span>
                  <Pencil size={13} />
                </button>
              ))
            ) : (
              <p className="muted small-text">识别到发言后会显示说话人。</p>
            )}
          </div>
          <div className="aside-card process-card">
            <h3>会议成果</h3>
            {[
              ["录音文件", hasAudio || live],
              ["文字记录", meeting.segments.length > 0],
              ["会议纪要", !!minutes],
              ["行动项", !!minutes?.action_items.length],
            ].map(([label, done]) => (
              <div
                className={`process-step ${done ? "complete" : ""}`}
                key={String(label)}
              >
                <span>{done ? <Check size={12} /> : <i />}</span>
                {label}
              </div>
            ))}
            <p className="aside-hint">每一条结论，都能回到原始发言。</p>
          </div>
        </aside>
      </div>
      {hasAudio && !live && (
        <div className="audio-player">
          <button
            className="play-button"
            aria-label={playing ? "暂停播放" : "播放录音"}
            onClick={() => {
              if (audio.current) {
                if (playing) audio.current.pause();
                else void audio.current.play();
              }
            }}
          >
            {playing ? (
              <Pause size={18} />
            ) : (
              <Play size={18} fill="currentColor" />
            )}
          </button>
          <div>
            <strong>会议录音</strong>
            <small>
              {duration(playTime)} / {duration(meeting.duration_ms)}
            </small>
          </div>
          <input
            type="range"
            aria-label="播放进度"
            min="0"
            max={meeting.duration_ms}
            value={Math.min(playTime, meeting.duration_ms)}
            onChange={(e) => {
              if (audio.current)
                audio.current.currentTime = Number(e.target.value) / 1000;
              setPlayTime(Number(e.target.value));
            }}
          />
          <span className="muted small-text">点击文字可定位播放</span>
          <audio
            ref={audio}
            src={asset(`/api/meetings/${id}/audio`)}
            onTimeUpdate={() =>
              setPlayTime((audio.current?.currentTime || 0) * 1000)
            }
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onEnded={() => setPlaying(false)}
          />
        </div>
      )}
      {speakerEdit && (
        <Modal
          title="修改说话人姓名"
          subtitle="历史及后续属于此人的发言，将同步使用新姓名。"
          onClose={() => {
            setSpeakerEdit(null);
            setMergeTarget("");
          }}
        >
          <Field label="姓名">
            <input
              autoFocus
              value={editName}
              maxLength={60}
              onChange={(e) => setEditName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void saveSpeaker();
              }}
            />
          </Field>
          <div className="modal-footer">
            <button
              className="button secondary"
              onClick={() => setSpeakerEdit(null)}
            >
              取消
            </button>
            <button
              className="button primary"
              onClick={saveSpeaker}
              disabled={!editName.trim()}
            >
              保存姓名
            </button>
          </div>
          {meeting.speakers.length > 1 && (
            <div className="speaker-merge">
              <Field label="如果此人与另一标签是同一个人，可合并">
                <select
                  value={mergeTarget}
                  onChange={(e) => setMergeTarget(e.target.value)}
                >
                  <option value="">选择保留的说话人</option>
                  {meeting.speakers
                    .filter((p) => p.id !== speakerEdit.id)
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                </select>
              </Field>
              <button
                className="button ghost small"
                disabled={!mergeTarget}
                onClick={async () => {
                  try {
                    setMeeting(
                      await api(`/api/meetings/${id}/speakers/merge`, "POST", {
                        source: speakerEdit.id,
                        target: mergeTarget,
                      }),
                    );
                    setSpeakerEdit(null);
                    setMergeTarget("");
                    toast("说话人已合并，姓名与关联发言同步更新。");
                  } catch (e) {
                    toast((e as Error).message);
                  }
                }}
              >
                <Merge size={14} />
                合并为所选说话人
              </button>
            </div>
          )}
        </Modal>
      )}
      {summaryEdit && (
        <Modal
          title="编辑会议总结"
          subtitle="每行一个要点。保存后保留原纪要版本。"
          onClose={() => setSummaryEdit(false)}
        >
          <Field label="总结要点">
            <textarea
              rows={9}
              value={summaryDraft}
              onChange={(e) => setSummaryDraft(e.target.value)}
            />
          </Field>
          <div className="modal-footer">
            <button
              className="button secondary"
              onClick={() => setSummaryEdit(false)}
            >
              取消
            </button>
            <button
              className="button primary"
              onClick={async () => {
                try {
                  setMeeting(
                    await api(`/api/meetings/${id}/minutes`, "PATCH", {
                      summary: summaryDraft.split("\n"),
                    }),
                  );
                  setSummaryEdit(false);
                  toast("总结已保存，原版本已保留。");
                } catch (e) {
                  toast((e as Error).message);
                }
              }}
            >
              保存总结
            </button>
          </div>
        </Modal>
      )}
      {renameTitle && (
        <Modal title="修改会议标题" onClose={() => setRenameTitle(false)}>
          <Field label="会议标题">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
            />
          </Field>
          <div className="modal-footer">
            <button
              className="button primary"
              onClick={async () => {
                try {
                  setMeeting(
                    await api(`/api/meetings/${id}`, "PATCH", { title }),
                  );
                  setRenameTitle(false);
                  onChanged();
                } catch (e) {
                  toast((e as Error).message);
                }
              }}
            >
              保存
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
function CheckCircle() {
  return (
    <span className="decision-check">
      <Check size={13} />
    </span>
  );
}
