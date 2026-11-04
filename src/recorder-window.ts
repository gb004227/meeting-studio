import { RecordingSession } from "./recording";
import "./types";
const bridge = window.desktop!;
const session = new RecordingSession(await bridge.getRuntime(), (state) =>
  bridge.reportRecording(state),
);
bridge.onRecordingCommand(async (command) => {
  try {
    if (command.type === "start")
      await session.start(command.meetingId!, command.source || "microphone");
    if (command.type === "pause") session.pause();
    if (command.type === "resume") session.resume();
    if (command.type === "stop") await session.stop();
  } catch (error) {
    bridge.reportRecording({
      active: false,
      error: String((error as Error).message),
      saving: false,
    });
  }
});
