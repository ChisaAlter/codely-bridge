#!/usr/bin/env node
/**
 * auth-gate.js — 给 codely-proxy 加一层 API Key 校验（公网暴露用）
 *
 * 背景：codely-proxy.js 本地侧没有任何入站鉴权，直接 0.0.0.0 暴露到公网
 *       等于任何人扫到端口就能白嫖你的 Codely 额度。本文件补上这一层。
 *
 * 设计：不修改上游任何文件（保持 git pull 可更新）。
 *       上游  codely-proxy.js  →  只监听 127.0.0.1:8791（内网，不可外网访问）
 *       本网关 auth-gate.js    →  监听 0.0.0.0:8790，校验 API Key 后转发
 *
 * 用法：
 *   node auth-gate.js
 *   环境变量：GATE_PORT(8790) GATE_BIND(0.0.0.0) UPSTREAM_PORT(8791)
 *                        CODELY_PROXY_API_KEY
 *
 * API Key 来源优先级：
 *   1. 环境变量 CODELY_PROXY_API_KEY
 *   2. 同目录 api-key.txt（首次运行自动生成，权限 600）
 *
 * 客户端用法（与 OpenAI 完全一致）：
 *   Authorization: Bearer <key>
 *   也接受 ?key=<key> 查询参数（部分客户端不好塞 header 时用）
 */
'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const HERE = __dirname;
const KEY_FILE = path.join(HERE, 'api-key.txt');

const PUBLIC_PORT = parseInt(process.env.GATE_PORT || '8790', 10);
const PUBLIC_BIND = process.env.GATE_BIND || '0.0.0.0';
const UPSTREAM_HOST = process.env.UPSTREAM_HOST || '127.0.0.1';
const UPSTREAM_PORT = parseInt(process.env.UPSTREAM_PORT || '8791', 10);

function ts() {
  const d = new Date();
  return `[${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}]`;
}
function log(...a) { console.log(ts(), '[gate]', ...a); }

/* ── API Key 读取或生成 ───────────────────────────────────────── */
function loadOrCreateKey() {
  const envKey = (process.env.CODELY_PROXY_API_KEY || '').trim();
  if (envKey) {
    if (envKey.length < 8) throw new Error('CODELY_PROXY_API_KEY 太短，至少 8 位');
    return { key: envKey, source: '环境变量 CODELY_PROXY_API_KEY' };
  }
  if (fs.existsSync(KEY_FILE)) {
    const k = fs.readFileSync(KEY_FILE, 'utf8').trim();
    if (k) return { key: k, source: `文件 ${path.basename(KEY_FILE)}` };
  }
  const k = 'sk-codely-' + crypto.randomBytes(24).toString('base64url');
  fs.writeFileSync(KEY_FILE, k + '\n', 'utf8');
  try { fs.chmodSync(KEY_FILE, 0o600); } catch { /* Windows 无 chmod */ }
  return { key: k, source: `文件 ${path.basename(KEY_FILE)}（首次运行自动生成）` };
}

/** 恒定时间比较，防时序侧信道 */
function safeEqual(a, b) {
  const ba = Buffer.from(String(a));
  const bb = Buffer.from(String(b));
  if (ba.length !== bb.length) {
    // 长度不同时也消耗相近时间，再做一次 dummy 比较
    crypto.timingSafeEqual(ba, ba);
    return false;
  }
  return crypto.timingSafeEqual(ba, bb);
}

/* ── 转发到上游 ───────────────────────────────────────────────── */
function forward(req, res, u, key) {
  const headers = Object.assign({}, req.headers);
  delete headers.host;
  delete headers['content-length']; // 由 pipe 重新决定
  // 上游不校验入站 key，替换成它自己的占位值，避免把网关 key 透传到上游日志
  headers.authorization = 'Bearer gate';
  headers.host = `${UPSTREAM_HOST}:${UPSTREAM_PORT}`;

  const opts = {
    host: UPSTREAM_HOST,
    port: UPSTREAM_PORT,
    path: u.pathname + u.search,
    method: req.method,
    headers,
  };

  const started = Date.now();
  const ip = (req.headers['x-forwarded-for'] || req.socket.remoteAddress || '').split(',')[0].trim();

  const up = http.request(opts, (ur) => {
    res.writeHead(ur.statusCode || 502, ur.headers);
    ur.pipe(res);
    ur.on('end', () => {
      log(`${ip} ${req.method} ${u.pathname} -> ${ur.statusCode} (${Date.now() - started}ms)`);
    });
  });

  up.on('error', (e) => {
    log(`${ip} ${req.method} ${u.pathname} -> 上游不可达: ${e.message}`);
    if (!res.headersSent) {
      res.writeHead(502, { 'Content-Type': 'application/json' });
    }
    res.end(JSON.stringify({
      error: {
        message: `上游 codely-proxy (${UPSTREAM_HOST}:${UPSTREAM_PORT}) 不可达，确认它已启动`,
        type: 'upstream_unavailable',
      },
    }));
  });

  req.on('aborted', () => up.destroy());
  req.pipe(up);
}

/* ── 主服务 ───────────────────────────────────────────────────── */
const { key: API_KEY, source: KEY_SOURCE } = loadOrCreateKey();

const server = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://gate');

  // /ping 不鉴权：只回 pong，不泄露任何账号/额度信息，供探活与监控使用
  if (u.pathname === '/ping') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end('{"pong":true}');
    return;
  }

  // 取 key：优先 Authorization 头，其次 ?key= 查询参数
  const authHeader = req.headers.authorization || '';
  const provided = authHeader.startsWith('Bearer ')
    ? authHeader.slice(7).trim()
    : (u.searchParams.get('key') || '');

  if (!provided || !safeEqual(provided, API_KEY)) {
    const ip = (req.headers['x-forwarded-for'] || req.socket.remoteAddress || '').split(',')[0].trim();
    log(`${ip} ${req.method} ${u.pathname} -> 401 (API Key 无效或缺失)`);
    res.writeHead(401, {
      'Content-Type': 'application/json',
      'WWW-Authenticate': 'Bearer realm="codely-proxy"',
    });
    res.end(JSON.stringify({
      error: {
        message: 'API Key 无效或缺失。请用 Authorization: Bearer <key> 或 ?key=<key>',
        type: 'invalid_request_error',
        code: 'invalid_api_key',
      },
    }));
    return;
  }

  forward(req, res, u, API_KEY);
});

server.listen(PUBLIC_PORT, PUBLIC_BIND, () => {
  log(`鉴权网关监听 http://${PUBLIC_BIND}:${PUBLIC_PORT}/v1`);
  log(`上游转发 → http://${UPSTREAM_HOST}:${UPSTREAM_PORT}（请确保上游只绑定 127.0.0.1）`);
  log(`API Key 来源: ${KEY_SOURCE}`);
  log(`API Key 值: ${API_KEY}`);
  log(`探活: http://<host>:${PUBLIC_PORT}/ping （无需鉴权，仅返回 pong）`);
});

server.on('error', (e) => {
  console.error(ts(), '[gate] 启动失败:', e.message);
  process.exit(1);
});
