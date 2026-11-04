const { contextBridge, ipcRenderer } = require("electron");
const subscribe = (name, callback) => {
  const listener = (_event, value) => callback(value);
  ipcRenderer.on(name, listener);
  return () => ipcRenderer.removeListener(name, listener);
};
contextBridge.exposeInMainWorld("desktop", {
  getRuntime: () => ipcRenderer.invoke("runtime"),
  getRecording: () => ipcRenderer.invoke("recording:get"),
  recordingCommand: (command) =>
    ipcRenderer.invoke("recording:command", command),
  onRecordingState: (callback) => subscribe("recording:state", callback),
  onRecordingCommand: (callback) => subscribe("recording:command", callback),
  reportRecording: (value) => ipcRenderer.send("recording:state", value),
  compact: () => ipcRenderer.invoke("recording:compact"),
  expand: () => ipcRenderer.invoke("recording:expand"),
  pickFile: () => ipcRenderer.invoke("file:pick"),
  exportFile: (value) => ipcRenderer.invoke("file:export", value),
  openData: () => ipcRenderer.invoke("data:open"),
  installModels: () => ipcRenderer.invoke("models:install"),
  onBackendError: (callback) => subscribe("backend:error", callback),
});
