import { useEffect, useState } from "react";
import {
  Cloud,
  HardDrive,
  BrainCircuit,
  ShieldCheck,
  CheckCircle2,
  Loader2,
  FolderOpen,
  RefreshCw,
  KeyRound,
  Save,
} from "lucide-react";
import { api } from "./api";
import { Field } from "./ui";

export default function Settings({
  toast,
  onSaved,
}: {
  toast: (message: string) => void;
  onSaved: () => void;
}) {
  const [settings, setSettings] = useState<Record<string, any> | null>(null);
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const load = () =>
    api("/api/settings")
      .then(setSettings)
      .catch((e) => toast(e.message));
  useEffect(() => {
    void load();
  }, []);
  const change = (key: string, value: any) =>
    setSettings((s) => ({ ...s, [key]: value }));
  async function save() {
    if (!settings) return;
    setBusy("save");
    try {
      const payload = {
        ...settings,
        ...Object.fromEntries(
          Object.entries(secrets).filter(([, value]) => value.trim()),
        ),
      };
      const result = await api("/api/settings", "PUT", payload);
      setSettings(result);
      setSecrets({});
      toast("设置已保存，密钥已在本机加密。");
      onSaved();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function check(kind: string) {
    setBusy(kind);
    try {
      const answer = await api("/api/settings/check", "POST", { kind });
      toast(answer.message);
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  if (!settings)
    return (
      <div className="loading-page">
        <Loader2 className="spin" />
        正在读取设置
      </div>
    );
  const keyField = (key: string, label: string) => (
    <Field
      label={label}
      hint={
        settings.secrets?.[key]
          ? "已安全保存；留空会保留现有密钥。"
          : "密钥只保存在本机的 Windows 加密存储中。"
      }
    >
      <div className="input-icon">
        <KeyRound size={16} />
        <input
          type="password"
          autoComplete="new-password"
          placeholder={
            settings.secrets?.[key] ? "•••••••••••• 已配置" : "粘贴 API Key"
          }
          value={secrets[key] || ""}
          onChange={(e) => setSecrets((s) => ({ ...s, [key]: e.target.value }))}
        />
        {settings.secrets?.[key] && (
          <CheckCircle2 size={17} className="green" />
        )}
      </div>
    </Field>
  );
  return (
    <div className="page settings-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">PREFERENCES</div>
          <h1>设置</h1>
          <p>配置一次，把注意力留给会议。</p>
        </div>
        <button className="button primary" onClick={save} disabled={!!busy}>
          {busy === "save" ? (
            <Loader2 size={17} className="spin" />
          ) : (
            <Save size={17} />
          )}
          保存设置
        </button>
      </div>
      <div className="notice quiet">
        <ShieldCheck size={19} />
        <span>
          音频与会议记录保存在本机。使用云端转写会发送音频；使用外部 AI
          纪要会发送文字。
        </span>
      </div>
      <section className="settings-card">
        <div className="section-title">
          <span className="section-icon blue">
            <Cloud size={21} />
          </span>
          <div>
            <h2>豆包语音识别</h2>
            <p>用于实时录音与云端文件转写</p>
          </div>
          <span
            className={`connection ${settings.secrets?.doubao_api_key ? "ready" : ""}`}
          >
            {settings.secrets?.doubao_api_key ? "密钥已配置" : "待配置"}
          </span>
        </div>
        {keyField("doubao_api_key", "语音识别 API Key")}
        <div className="field-grid">
          <Field label="实时识别资源">
            <select
              value={settings.doubao_realtime_resource}
              onChange={(e) =>
                change("doubao_realtime_resource", e.target.value)
              }
            >
              <option value="volc.seedasr.sauc.duration">
                豆包 2.0 · 按时长
              </option>
              <option value="volc.seedasr.sauc.concurrent">
                豆包 2.0 · 按并发
              </option>
            </select>
          </Field>
          <Field label="文件转写通道">
            <select
              value={settings.doubao_file_mode}
              onChange={(e) => {
                change("doubao_file_mode", e.target.value);
                change(
                  "doubao_file_resource",
                  e.target.value === "standard"
                    ? "volc.seedasr.auc"
                    : "volc.bigasr.auc_turbo",
                );
              }}
            >
              <option value="stream">
                豆包 2.0 · 复用实时权限，无需额外存储
              </option>
              <option value="flash">文件极速版 · 需开通极速识别权限</option>
              <option value="standard">文件标准版 · 私有 TOS 临时上传</option>
            </select>
          </Field>
        </div>
        <p className="field-help">
          文件权限与实时权限分开开通。复用实时权限的通道可直接转写本机录音，处理时间取决于音频长度和服务速度。
        </p>
        <p className="field-help">
          {settings.speaker_helper_ready
            ? "本地说话人辅助校正已就绪，会结合声音特征分人；录音时文字先显示，人员标签随后补齐。"
            : "当前使用豆包返回的说话人标签；准备本地模型后可增强分人校正。"}
        </p>
        <div className="row">
          <button
            className="button secondary small"
            disabled={!!busy}
            onClick={() => check("realtime")}
          >
            {busy === "realtime" ? (
              <Loader2 size={15} className="spin" />
            ) : (
              <RefreshCw size={15} />
            )}
            检查实时连接
          </button>
          {settings.doubao_file_mode === "flash" && (
            <button
              className="button secondary small"
              disabled={!!busy}
              onClick={() => check("file")}
            >
              检查极速版权限
            </button>
          )}
          <span className="muted small-text">
            使用短静音样本验证，可能产生少量语音调用费用。
          </span>
        </div>
      </section>
      <section className="settings-card">
        <div className="section-title">
          <span className="section-icon teal">
            <HardDrive size={21} />
          </span>
          <div>
            <h2>MOSS 本地转写</h2>
            <p>音频留在本机，支持文件转写与本地流式字幕</p>
          </div>
          <span className={`connection ${settings.moss_ready ? "ready" : ""}`}>
            {settings.moss_ready ? "模型文件已就绪" : "待准备模型"}
          </span>
        </div>
        <Field label="模型目录">
          <input
            value={settings.moss_path}
            onChange={(e) => change("moss_path", e.target.value)}
          />
        </Field>
        <div className="field-grid">
          <Field label="本地推理 Python">
            <input
              value={settings.moss_python}
              onChange={(e) => change("moss_python", e.target.value)}
            />
          </Field>
          <Field label="推理设备">
            <select
              value={settings.moss_device}
              onChange={(e) => change("moss_device", e.target.value)}
            >
              <option value="cpu">CPU · 兼容模式，速度取决于电脑</option>
              <option value="auto">自动选择可用设备</option>
              <option value="cuda">NVIDIA CUDA</option>
            </select>
          </Field>
        </div>
        <p className="field-help">
          {settings.local_live_ready
            ? "本地流式字幕组件已就绪：会中使用轻量识别预览，结束后由 MOSS 完整精修。"
            : "本地流式字幕组件尚未准备，当前使用较慢的 MOSS 分段预览，可点击准备 / 修复本地模型。"}
          文件转写由 MOSS 在本机处理，CPU 可能较慢；已修改的人名与原稿会保留。
        </p>
        <div className="row">
          <button
            className="button secondary small"
            onClick={() => check("moss")}
            disabled={!!busy}
          >
            <RefreshCw size={15} />
            检查本地环境
          </button>
          {window.desktop && (
            <button
              className="button ghost small"
              onClick={async () => {
                try {
                  toast((await window.desktop!.installModels()).message);
                } catch (e) {
                  toast((e as Error).message);
                }
              }}
            >
              准备 / 修复本地模型
            </button>
          )}
        </div>
      </section>
      <section className="settings-card">
        <div className="section-title">
          <span className="section-icon violet">
            <BrainCircuit size={21} />
          </span>
          <div>
            <h2>AI 会议纪要</h2>
            <p>独立文本模型，可与任意转写引擎搭配</p>
          </div>
          <span
            className={`connection ${settings.secrets?.llm_api_key && settings.llm_model ? "ready" : ""}`}
          >
            {settings.secrets?.llm_api_key && settings.llm_model
              ? "已配置"
              : "基础提取可用"}
          </span>
        </div>
        <div className="field-grid">
          <Field
            label="兼容接口地址"
            hint="填写包含 /v1 或 /api/v3 的服务地址。"
          >
            <input
              placeholder="https://your-provider.example/v1"
              value={settings.llm_base_url}
              onChange={(e) => change("llm_base_url", e.target.value)}
            />
          </Field>
          <Field label="模型 ID">
            <input
              placeholder="服务商提供的文本模型 ID"
              value={settings.llm_model}
              onChange={(e) => change("llm_model", e.target.value)}
            />
          </Field>
        </div>
        {keyField("llm_api_key", "纪要模型 API Key")}
        <div className="notice quiet">
          <BrainCircuit size={18} />
          <span>
            未配置文本模型时，软件会从原文提取基础要点、明确决策和候选行动项，并标明“基础纪要”，便于你确认整理。
          </span>
        </div>
      </section>
      {settings.doubao_file_mode === "standard" && (
        <section className="settings-card">
          <div className="section-title">
            <span className="section-icon blue">
              <Cloud size={21} />
            </span>
            <div>
              <h2>标准版临时上传</h2>
              <p>仅在选择文件标准版时使用私有 TOS</p>
            </div>
          </div>
          <div className="field-grid">
            <Field label="TOS Region">
              <input
                value={settings.tos_region}
                onChange={(e) => change("tos_region", e.target.value)}
                placeholder="cn-beijing"
              />
            </Field>
            <Field label="私有桶名称">
              <input
                value={settings.tos_bucket}
                onChange={(e) => change("tos_bucket", e.target.value)}
              />
            </Field>
          </div>
          <Field label="TOS 公网 Endpoint">
            <input
              value={settings.tos_endpoint}
              onChange={(e) => change("tos_endpoint", e.target.value)}
              placeholder="tos-cn-beijing.volces.com"
            />
          </Field>
          {keyField("tos_access_key", "TOS Access Key")}
          {keyField("tos_secret_key", "TOS Secret Key")}
          <p className="field-help">
            识别结束后软件尝试删除临时对象；建议在桶中为 meeting-studio/
            前缀设置生命周期规则。
          </p>
        </section>
      )}
      <section className="settings-card data-card">
        <div>
          <h2>本机数据目录</h2>
          <p>{settings.data_directory}</p>
        </div>
        <button
          className="button secondary small"
          onClick={() => window.desktop?.openData()}
        >
          <FolderOpen size={16} />
          打开目录
        </button>
      </section>
    </div>
  );
}
