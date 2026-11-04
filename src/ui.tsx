import type { ReactNode } from "react";
import { X, AudioLines, Cloud, HardDrive, Loader2 } from "lucide-react";

export function duration(ms = 0) {
  const s = Math.floor(ms / 1000);
  return s >= 3600
    ? `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`
    : `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
export function when(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}
export const statusText: Record<string, string> = {
  ready: "待开始",
  queued: "等待处理",
  recording: "录音中",
  transcribing: "转写中",
  transcribed: "转写完成",
  completed: "已完成",
  failed: "处理失败",
  partial_failed: "部分完成",
};
export function Status({ status }: { status: string }) {
  const busy = ["recording", "transcribing", "queued"].includes(status);
  return (
    <span className={`status status-${status}`}>
      {busy ? <Loader2 size={12} className="spin" /> : <i />}
      {statusText[status] || status}
    </span>
  );
}
export function Engine({ engine }: { engine: string }) {
  return (
    <span className="engine">
      {engine === "moss" ? <HardDrive size={13} /> : <Cloud size={13} />}{" "}
      {engine === "moss" ? "MOSS 本地" : "豆包云端"}
    </span>
  );
}
export function Logo({ small = false }: { small?: boolean }) {
  return (
    <div className={`brand ${small ? "brand-small" : ""}`}>
      <span className="brand-mark">
        <AudioLines size={small ? 19 : 24} />
      </span>
      <span>
        听会<small>MEETING STUDIO</small>
      </span>
    </div>
  );
}
export function Modal({
  title,
  subtitle,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        className={`modal ${wide ? "modal-wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="modal-heading">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button className="icon-button" aria-label="关闭" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function Wave({
  level = 0,
  paused = false,
}: {
  level?: number;
  paused?: boolean;
}) {
  return (
    <div
      className={`wave ${paused ? "paused" : ""}`}
      aria-label={paused ? "已暂停" : "录音声波"}
    >
      {Array.from({ length: 30 }, (_, i) => (
        <i
          key={i}
          style={{
            height: `${paused ? 4 : 5 + (Math.sin(i * 1.37 + 1) * 0.5 + 0.5) * Math.max(level, 0.07) * 55}px`,
            animationDelay: `${i * 38}ms`,
          }}
        />
      ))}
    </div>
  );
}
export function Empty({
  icon,
  title,
  description,
  children,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">{icon}</span>
      <h3>{title}</h3>
      <p>{description}</p>
      {children}
    </div>
  );
}
