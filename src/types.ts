export type Runtime = {
  baseUrl: string;
  token: string;
  dataDirectory?: string;
};
export type Speaker = {
  id: string;
  name: string;
  color: number;
  name_revision: number;
};
export type Segment = {
  id: string;
  version_id: string;
  speaker_id: string | null;
  start_ms: number;
  end_ms: number;
  text: string;
  edited: number;
};
export type ActionItem = {
  id: string;
  task: string;
  owner_speaker_id?: string | null;
  owner_mentioned_as?: string | null;
  due_date?: string | null;
  deliverable?: string | null;
  status: string;
  evidence_segment_ids: string[];
  source?: string;
};
export type Minutes = {
  id: string;
  source_version: string;
  kind: string;
  stale: boolean;
  data: {
    title: string;
    summary: string[];
    topics: { title: string; points: string[] }[];
    decisions: { id: string; text: string; evidence_segment_ids: string[] }[];
    action_items: ActionItem[];
    pending_questions: string[];
    notice?: string;
    generator?: string;
  };
};
export type Meeting = {
  id: string;
  title: string;
  mode: "realtime" | "file";
  engine: "doubao" | "moss";
  caption_engine?: "local_stream" | "moss_batch" | "doubao" | null;
  status: string;
  created_at: string;
  updated_at: string;
  duration_ms: number;
  audio_path?: string;
  filename?: string;
  error: string;
  current_version: string;
  hotwords: string;
  auto_minutes: boolean;
  speaker_count?: number;
  speakers: Speaker[];
  segments: Segment[];
  versions: { id: string; kind: string; status: string; created_at: string }[];
  minutes: Minutes | null;
  tasks: {
    id: string;
    kind: string;
    state: string;
    stage: string;
    error: string;
  }[];
};
export type RecordingState = {
  active: boolean;
  meetingId?: string;
  paused: boolean;
  elapsed: number;
  level: number;
  saving?: boolean;
  saved?: boolean;
  error?: string;
};
export type RecordingCommand = {
  type: "start" | "pause" | "resume" | "stop";
  meetingId?: string;
  source?: "microphone" | "system" | "both";
};
declare global {
  interface Window {
    desktop?: {
      getRuntime: () => Promise<Runtime>;
      getRecording: () => Promise<RecordingState>;
      recordingCommand: (command: RecordingCommand) => Promise<unknown>;
      onRecordingState: (cb: (value: RecordingState) => void) => () => void;
      onRecordingCommand: (
        cb: (command: RecordingCommand) => void,
      ) => () => void;
      reportRecording: (state: Partial<RecordingState>) => void;
      compact: () => Promise<unknown>;
      expand: () => Promise<unknown>;
      pickFile: () => Promise<string | null>;
      exportFile: (value: {
        meetingId: string;
        kind: string;
        title: string;
      }) => Promise<boolean>;
      openData: () => Promise<unknown>;
      installModels: () => Promise<{ ok: boolean; message: string }>;
      onBackendError: (cb: (message: string) => void) => () => void;
    };
  }
}
