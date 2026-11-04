# 听会 · GitHub 发布版安装说明

适用系统：Windows 11 x64。主程序默认使用 CPU，包含两套独立 Python 环境和 C++ 运行库，不需要安装 Python、Node.js 或 uv。

## 下载文件

到 https://github.com/gb004227/meeting-studio/releases/latest 下载同一版本的两个文件：

1. `TingHui-0.1.2-Windows-x64-program.zip`：程序包，含桌面程序和运行环境。
2. `TingHui-0.1.2-models.zip`：模型包，含 MOSS、实时字幕及说话人辅助模型。

同一发布页还提供 `SHA256SUMS.txt` 和本文的纯文本版 `INSTALL.zh-CN.txt`。GitHub 自动生成的 `Source code` 下载项是开发源码，日常使用请下载上面两个 ZIP。

## 解压与合并

1. 将程序包“全部解压”到短路径，例如 `D:\听会`，得到 `听会-0.1.2-Windows-x64` 文件夹。
2. 将模型包“全部解压”，得到 `models` 文件夹。
3. 把整个 `models` 文件夹复制到程序文件夹里的 `resources` 目录。最终结构如下：

```text
听会-0.1.2-Windows-x64/
  听会.exe
  resources/
    app/
    backend/
    python/
    moss-python/
    models/
      MOSS-Transcribe-Diarize/
      auxiliary/
        paraformer-streaming/
        camplusplus/
```

模型的 `config.json` 应位于 `resources\models\MOSS-Transcribe-Diarize\config.json`，请避免出现 `resources\models\models` 的重复目录层级。首次安装建议预留至少 10GB 空间，用于下载包、解压内容和后续录音。

4. 双击 `听会.exe`。保持整个程序目录完整。
5. 在设置页检查 MOSS、本地字幕和说话人辅助组件就绪状态，先用一段短录音验证字幕和保存。

## 选择识别模式

- **MOSS 本地**：安装模型包后直接选择。会中由轻量模型显示本地流式字幕，停止后 MOSS 精修；CPU 处理速度取决于电脑性能。音频不自动上传云端。
- **豆包云端**：在“设置 → 豆包语音识别”填写自己的 API Key 并检查连接。语音服务按账号权限和用量计费。默认文件模式复用实时识别权限，音频按实际时长发送。
- **会议纪要**：默认提供基础纪要及候选行动项。调用外部 AI 文本模型需要在“AI 会议纪要”另填接口地址、模型 ID 和独立 Key。

## 会议与密钥

发布文件不包含开发者的私人录音、会议数据库或密钥。新电脑使用新的会议库，数据保存在该 Windows 用户的 `%LOCALAPPDATA%\MeetingStudio`。

API Key 在本机按 Windows 用户加密保存，换电脑后请重新填写。不要把密钥写进 GitHub 仓库。

## 更新

升级程序时可将新程序包解压到新目录，再把已有的 `resources\models` 复制过去。只有发布说明明确更新模型时才需要重新下载模型包。若同时打开多个版本，请先关闭前一个版本。

旧会议仍保存在当前 Windows 用户的数据目录；完整跨电脑迁移会议需要单独迁移数据库和录音，并修正录音路径。
