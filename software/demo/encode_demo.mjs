// Turns the numbered JPEG frames from compose_demo.py into an H.264 MP4 using the encoder that is already inside Chrome
// (MediaRecorder), so no ffmpeg is needed. It plays the frames onto a canvas in real time (a 2 minute video takes 2 minutes) and
// records the canvas stream. Usage:  node software/demo/encode_demo.mjs framesDir out.mp4 [fps]
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { readdirSync, readFileSync, writeFileSync, rmSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import os from "node:os";

const [framesDir, outPath, fpsArg] = process.argv.slice(2);
if (!framesDir || !outPath) { console.error("usage: node encode_demo.mjs framesDir out.mp4 [fps]"); process.exit(2); }
const FPS = Number(fpsArg ?? 30);
const CHROME = process.env.CHROME ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const frames = readdirSync(framesDir).filter((f) => f.endsWith(".jpg")).sort();

const PAGE = `<!doctype html><meta charset=utf-8><body style="margin:0;background:#000"><canvas id=c width=1920 height=1080></canvas><script>
const FPS = ${FPS};
(async () => {
  const frames = await (await fetch('/frames.json')).json();
  const c = document.getElementById('c'), ctx = c.getContext('2d');
  const stream = c.captureStream(FPS);
  const mime = ['video/mp4;codecs=avc1.640028', 'video/mp4;codecs=avc1', 'video/mp4'].find(t => MediaRecorder.isTypeSupported(t));
  const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 9000000 });
  const chunks = [];
  rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
  const stopped = new Promise(r => rec.onstop = r);
  const cache = new Map();
  const want = i => { if (i < frames.length && !cache.has(i)) { const im = new Image(); im.src = '/f/' + frames[i]; cache.set(i, im); } };
  for (let i = 0; i < 90; i++) want(i);
  await new Promise(r => setTimeout(r, 1500));
  rec.start(1000);
  const t0 = performance.now();
  let shown = -1, late = 0;
  await new Promise(done => {
    const tick = () => {
      const i = Math.floor((performance.now() - t0) * FPS / 1000);
      if (i >= frames.length) return done();
      for (let k = i; k < i + 90; k++) want(k);
      for (const key of cache.keys()) if (key < i - 3) cache.delete(key);
      const im = cache.get(i);
      if (i !== shown) {
        if (im && im.complete && im.naturalWidth) { ctx.drawImage(im, 0, 0); shown = i; } else late++;
      }
      setTimeout(tick, 8);
    };
    tick();
  });
  await new Promise(r => setTimeout(r, 400));
  rec.stop();
  await stopped;
  const blob = new Blob(chunks, { type: mime });
  await fetch('/out', { method: 'POST', body: blob });
  window.__done = JSON.stringify({ mime, bytes: blob.size, late });
})();
</script>`;

let result;
const server = createServer((req, res) => {
  if (req.url === "/") { res.setHeader("content-type", "text/html"); res.end(PAGE); }
  else if (req.url === "/frames.json") { res.setHeader("content-type", "application/json"); res.end(JSON.stringify(frames)); }
  else if (req.url.startsWith("/f/")) { res.setHeader("content-type", "image/jpeg"); res.end(readFileSync(join(framesDir, req.url.slice(3)))); }
  else if (req.url === "/out" && req.method === "POST") {
    const parts = [];
    req.on("data", (d) => parts.push(d));
    req.on("end", () => { writeFileSync(outPath, Buffer.concat(parts)); res.end("ok"); });
  } else { res.statusCode = 404; res.end(); }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const sport = server.address().port;
const port = 9800 + Math.floor(Math.random() * 100);
const profile = join(os.tmpdir(), `encode-chrome-${Date.now()}`);
mkdirSync(profile, { recursive: true });
const proc = spawn(CHROME, [`--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "--headless=new", "--no-first-run", "--mute-audio",
  "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows", "--window-size=1920,1080", `http://127.0.0.1:${sport}/`], { stdio: "ignore" });

let ws;
for (let i = 0; i < 100 && !ws; i++) {
  try {
    const t = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((x) => x.type === "page");
    if (t) { ws = new WebSocket(t.webSocketDebuggerUrl); await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; }); }
  } catch { ws = undefined; await new Promise((r) => setTimeout(r, 200)); }
}
let id = 0; const pending = new Map();
ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } };
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
console.log(`encoding ${frames.length} frames at ${FPS} fps (about ${(frames.length / FPS).toFixed(0)} s in real time)...`);
for (;;) {
  await new Promise((r) => setTimeout(r, 2000));
  const r = await send("Runtime.evaluate", { expression: "window.__done || ''", returnByValue: true });
  if (r?.result?.value) { result = r.result.value; break; }
}
console.log("done", result);
ws.close(); proc.kill(); server.close();
await new Promise((r) => setTimeout(r, 500));
try { rmSync(profile, { recursive: true, force: true }); } catch { /* chrome may still hold files */ }
