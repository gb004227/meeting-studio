import type { Runtime } from "./types";
let runtime: Runtime = { baseUrl: "http://127.0.0.1:9011", token: "" };
export async function initialize() {
  if (window.desktop) runtime = await window.desktop.getRuntime();
  return runtime;
}
export function endpoint(path: string) {
  return runtime.baseUrl + path;
}
export function asset(path: string) {
  return (
    endpoint(path) +
    (path.includes("?") ? "&" : "?") +
    "token=" +
    encodeURIComponent(runtime.token)
  );
}
export function wsUrl(path: string) {
  return asset(path).replace(/^http/, "ws");
}
export async function api<T = any>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  const response = await fetch(endpoint(path), {
    method,
    headers: {
      "x-meeting-token": runtime.token,
      ...(data instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
    },
    body:
      data === undefined
        ? undefined
        : data instanceof FormData
          ? data
          : JSON.stringify(data),
  });
  if (!response.ok) {
    let message = "请求失败";
    try {
      const value = await response.json();
      message = value.detail || message;
    } catch {}
    throw new Error(message);
  }
  return response.json();
}
