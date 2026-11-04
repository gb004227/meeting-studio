import type { RecordingState, Runtime } from "./types";

const workletSource = `class PCMProcessor extends AudioWorkletProcessor {
 constructor(){super();this.buffer=new Int16Array(3200);this.position=0;this.enabled=true;this.port.onmessage=e=>{if(e.data==='flush'){if(this.position){const copy=this.buffer.slice(0,this.position);this.port.postMessage({pcm:copy.buffer,level:0},[copy.buffer]);}this.position=0;}else this.enabled=e.data==='resume';};}
 process(inputs){const channel=inputs[0]&&inputs[0][0];if(!channel||!this.enabled)return true;let level=0;for(let i=0;i<channel.length;i++){const v=Math.max(-1,Math.min(1,channel[i]));level+=v*v;this.buffer[this.position++]=v<0?v*32768:v*32767;if(this.position===this.buffer.length){const copy=this.buffer.slice();this.port.postMessage({pcm:copy.buffer,level:Math.sqrt(level/channel.length)},[copy.buffer]);this.position=0;}}return true;}
}registerProcessor('pcm-processor',PCMProcessor);`;

export class RecordingSession {
  context: AudioContext | null = null;
  streams: MediaStream[] = [];
  node: AudioWorkletNode | null = null;
  socket: WebSocket | null = null;
  state: RecordingState = {
    active: false,
    paused: false,
    elapsed: 0,
    level: 0,
  };
  timer: ReturnType<typeof setInterval> | null = null;
  samples = 0;
  stopping = false;
  runtime: Runtime;
  onState: (state: RecordingState) => void;
  constructor(runtime: Runtime, onState: (state: RecordingState) => void) {
    this.runtime = runtime;
    this.onState = onState;
  }
  emit(value: Partial<RecordingState>) {
    this.state = { ...this.state, ...value };
    this.onState(this.state);
  }
  async start(meetingId: string, source: "microphone" | "system" | "both") {
    if (this.state.active) throw new Error("已有录音正在进行");
    this.samples = 0;
    this.stopping = false;
    try {
      if (source !== "system")
        this.streams.push(
          await navigator.mediaDevices.getUserMedia({
            audio: {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            },
            video: false,
          }),
        );
      if (source !== "microphone") {
        const stream = await navigator.mediaDevices.getDisplayMedia({
          audio: true,
          video: true,
        });
        if (
          !stream.getAudioTracks().some((track) => track.readyState === "live")
        ) {
          stream.getTracks().forEach((t) => t.stop());
          throw new Error("未获取电脑声音，请检查系统声音采集权限。");
        }
        this.streams.push(stream);
      }
      this.context = new AudioContext({ sampleRate: 16000 });
      if (this.context.sampleRate !== 16000)
        throw new Error("当前音频设备不支持 16kHz 录音，请选择其他输入设备。");
      const url = URL.createObjectURL(
        new Blob([workletSource], { type: "application/javascript" }),
      );
      await this.context.audioWorklet.addModule(url);
      URL.revokeObjectURL(url);
      const mix = this.context.createGain();
      mix.gain.value = source === "both" ? 0.5 : 1;
      mix.channelCount = 1;
      mix.channelCountMode = "explicit";
      mix.channelInterpretation = "speakers";
      for (const stream of this.streams)
        this.context
          .createMediaStreamSource(new MediaStream(stream.getAudioTracks()))
          .connect(mix);
      this.node = new AudioWorkletNode(this.context, "pcm-processor");
      mix.connect(this.node);
      const silent = this.context.createGain();
      silent.gain.value = 0;
      this.node.connect(silent).connect(this.context.destination);
      const socket = new WebSocket(
        this.runtime.baseUrl.replace(/^http/, "ws") +
          `/api/meetings/${meetingId}/record?token=${encodeURIComponent(this.runtime.token)}`,
      );
      this.socket = socket;
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(
          () => reject(new Error("录音服务连接超时")),
          15000,
        );
        socket.onerror = () => {
          clearTimeout(timer);
          reject(new Error("无法连接本地录音服务"));
        };
        socket.onmessage = (event) => {
          const result = JSON.parse(event.data);
          if (result.type === "ready") {
            clearTimeout(timer);
            resolve();
          } else if (result.type === "error") {
            clearTimeout(timer);
            reject(new Error(result.message));
          }
        };
      });
      socket.onmessage = (event) => {
        const value = JSON.parse(event.data);
        if (value.type === "saved") {
          this.emit({ active: false, saving: false, saved: true, level: 0 });
          socket.close();
        } else if (value.type === "error") this.emit({ error: value.message });
      };
      socket.onclose = () => {
        if (this.state.active) {
          this.emit({
            active: false,
            saving: false,
            error: "本地录音连接中断，已保存的数据仍保留。",
          });
          void this.cleanup();
        }
      };
      this.node.port.onmessage = (event) => {
        if (this.state.paused || this.stopping) return;
        const { pcm, level } = event.data;
        if (socket.readyState === WebSocket.OPEN) {
          if (socket.bufferedAmount > 4 * 1024 * 1024) {
            this.emit({ error: "本地服务积压，请停止并检查录音。" });
            return;
          }
          socket.send(pcm);
          this.samples += pcm.byteLength / 2;
          this.emit({
            elapsed: Math.floor(this.samples / 16),
            level: Math.min(1, level * 5),
          });
        }
      };
      this.emit({
        active: true,
        paused: false,
        elapsed: 0,
        meetingId,
        saved: false,
        error: undefined,
        saving: false,
      });
      await this.context.resume();
    } catch (error) {
      await this.cleanup();
      throw error;
    }
  }
  pause() {
    this.node?.port.postMessage("pause");
    this.node?.port.postMessage("flush");
    setTimeout(() => this.emit({ paused: true, level: 0 }), 50);
  }
  resume() {
    this.node?.port.postMessage("resume");
    this.emit({ paused: false });
  }
  async stop() {
    if (!this.state.active || this.stopping) return;
    this.emit({ saving: true });
    // Flush the partial PCM block while the message handler is still accepting audio.
    this.node?.port.postMessage("flush");
    await new Promise((r) => setTimeout(r, 80));
    this.stopping = true;
    if (this.socket?.readyState === WebSocket.OPEN)
      this.socket.send(JSON.stringify({ type: "stop" }));
    await this.cleanup(false);
  }
  async cleanup(closeSocket = true) {
    this.node?.disconnect();
    this.node = null;
    for (const stream of this.streams)
      stream.getTracks().forEach((t) => t.stop());
    this.streams = [];
    if (this.context) {
      await this.context.close();
      this.context = null;
    }
    if (closeSocket) {
      this.socket?.close();
      this.socket = null;
    }
  }
}
