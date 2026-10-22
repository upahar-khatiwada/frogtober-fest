// @ts-check
/**
 * `test` for the E2E spec. Under Node it is Playwright's own. Under Bun (this repo is Bun only, CLAUDE.md) Playwright's
 * Chromium launch hangs on Windows: it talks to the browser over extra stdio pipes (`--remote-debugging-pipe`), which
 * Bun's child processes do not provide. So under Bun the worker starts Playwright's Chromium itself with a DevTools
 * port and attaches over CDP; contexts, pages, downloads and tracing work as usual.
 *
 * Attaching needs one more fix: Bun's node:http reports a WebSocket handshake as a plain `101` response and never
 * emits `upgrade`, which Playwright's bundled `ws` client waits for (Bun 1.3, observed 2026-10-22). `shimWebSocketUpgrade`
 * does the handshake for such requests over a raw net socket and emits `upgrade` like Node does. Test code only.
 */
import { spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import { mkdtempSync, rmSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";

import { test as base, chromium } from "@playwright/test";

const UNDER_BUN = typeof process.versions.bun === "string";

function shimWebSocketUpgrade() {
  const original = http.request;
  /** @type {any} */ (http).request = function (/** @type {any} */ opts, /** @type {any} */ ...rest) {
    const headers = (opts && typeof opts === "object" && opts.headers) || {};
    const isUpgrade = Object.entries(headers).some(
      ([k, v]) => k.toLowerCase() === "upgrade" && String(v).toLowerCase() === "websocket",
    );
    if (!isUpgrade || opts instanceof URL) return original.call(http, opts, ...rest);

    const req = /** @type {any} */ (new EventEmitter());
    const host = opts.hostname ?? opts.host ?? "127.0.0.1";
    const port = Number(opts.port ?? 80);
    /** @type {net.Socket | null} */
    let socket = null;
    req.setTimeout = () => req;
    req.abort = req.destroy = () => socket?.destroy();
    req.end = () => {
      socket = net.connect({ host, port });
      const s = socket;
      s.once("connect", () => {
        const lines = [`GET ${opts.path ?? "/"} HTTP/1.1`, `Host: ${host}:${port}`];
        for (const [k, v] of Object.entries(headers)) lines.push(`${k}: ${v}`);
        s.write(`${lines.join("\r\n")}\r\n\r\n`);
      });
      let buffer = Buffer.alloc(0);
      const onData = (/** @type {Buffer} */ chunk) => {
        buffer = Buffer.concat([buffer, chunk]);
        const end = buffer.indexOf("\r\n\r\n");
        if (end < 0) return;
        s.removeListener("data", onData);
        const [status, ...fields] = buffer.subarray(0, end).toString("latin1").split("\r\n");
        const statusCode = Number(status.split(" ")[1]);
        /** @type {Record<string, string>} */
        const resHeaders = {};
        /** @type {string[]} */
        const rawHeaders = [];
        for (const field of fields) {
          const i = field.indexOf(":");
          if (i <= 0) continue;
          const [name, value] = [field.slice(0, i).trim(), field.slice(i + 1).trim()];
          resHeaders[name.toLowerCase()] = value;
          rawHeaders.push(name, value);
        }
        const res = { statusCode, statusMessage: status.split(" ").slice(2).join(" "), headers: resHeaders, rawHeaders };
        if (statusCode === 101) req.emit("upgrade", res, s, buffer.subarray(end + 4));
        else req.emit("error", new Error(`WebSocket handshake failed: HTTP ${statusCode}`));
      };
      s.on("data", onData);
      s.on("error", (e) => req.emit("error", e));
    };
    return req;
  };
}

if (UNDER_BUN) shimWebSocketUpgrade();

async function launchOverCdp() {
  const dir = mkdtempSync(path.join(tmpdir(), "tenderly-e2e-"));
  const proc = spawn(
    chromium.executablePath(),
    [
      "--headless=new",
      "--remote-debugging-port=0",
      `--user-data-dir=${dir}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-extensions",
      "--disable-background-networking",
      "about:blank",
    ],
    { stdio: ["ignore", "ignore", "pipe"] },
  );
  /** @type {string} */
  const endpoint = await new Promise((resolve, reject) => {
    let log = "";
    const timer = setTimeout(() => reject(new Error(`Chromium did not start:\n${log}`)), 60_000);
    proc.stderr?.on("data", (chunk) => {
      log += chunk;
      const m = log.match(/DevTools listening on (ws:\/\/\S+)/);
      if (m) {
        clearTimeout(timer);
        resolve(m[1]);
      }
    });
    proc.on("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`Chromium exited (${code}):\n${log}`));
    });
  });
  const browser = await chromium.connectOverCDP(endpoint);
  const close = async () => {
    await browser.close().catch(() => {});
    proc.kill();
    try {
      rmSync(dir, { recursive: true, force: true });
    } catch {
      // Chromium may still hold the profile for a moment; the OS temp dir is cleaned eventually.
    }
  };
  return { browser, close };
}

export const test = UNDER_BUN
  ? base.extend({
      browser: [
        async ({}, use) => {
          const { browser, close } = await launchOverCdp();
          await use(browser);
          await close();
        },
        { scope: "worker" },
      ],
    })
  : base;

export { expect } from "@playwright/test";
