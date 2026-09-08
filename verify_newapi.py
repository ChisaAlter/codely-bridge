#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""经 new-api 端到端验证 codely 渠道是否真的可用。

从库里取一个启用中的 token 用于测试（只在本脚本内部使用，不打印），
然后走 new-api 的 /v1/models 与 /v1/chat/completions。

只输出结论，不输出任何密钥。
"""
import json
import sqlite3
import sys
import urllib.error
import urllib.request

DB = '/opt/new-api/data/one-api.db'
NEWAPI = 'http://127.0.0.1:3390'
TEST_MODEL = 'codely-core'


def pick_token(cur):
    cur.execute('SELECT key, name, status, remain_quota, unlimited_quota FROM tokens')
    rows = cur.fetchall()
    # 优先：启用 + 无限额度；其次：启用
    enabled = [r for r in rows if r[2] == 1]
    unlimited = [r for r in enabled if r[4]]
    pool = unlimited or enabled
    if not pool:
        return None, '没有启用中的 token'
    r = pool[0]
    return r[0], 'token#%s (unlimited=%s, remain=%s)' % (r[1], r[4], r[3])


def req(path, token, payload=None, timeout=180):
    url = NEWAPI + path
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    r = urllib.request.Request(url, data=data, method='POST' if data else 'GET')
    r.add_header('Authorization', 'Bearer ' + token)
    r.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:
        return 0, '%s: %s' % (type(e).__name__, e)


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    token, desc = pick_token(cur)
    con.close()
    if not token:
        print('跳过: ' + desc)
        return
    print('使用: ' + desc)
    print()

    print('=== 1) GET /v1/models（应含 codely-* 模型）===')
    code, body = req('/v1/models', token, timeout=60)
    print('HTTP', code)
    if code == 200:
        try:
            ids = [m['id'] for m in json.loads(body).get('data', [])]
            hit = [i for i in ids if i.startswith('codely') or i in ('KIMI-K3', 'GLM-5.3-FLASH')]
            print('模型总数:', len(ids))
            print('codely 相关:', hit)
        except Exception as e:
            print('解析失败:', e, body[:200])
    else:
        print(body[:400])
    print()

    print('=== 2) POST /v1/chat/completions (model=%s) ===' % TEST_MODEL)
    payload = {
        'model': TEST_MODEL,
        'messages': [{'role': 'user', 'content': '用一句话说明你已通过 new-api 接入'}],
        # codely-core 是推理模型：max_tokens 太小会被 reasoning_content 吃光，
        # 导致 content 为空、finish_reason=length。给足余量。
        'max_tokens': 3000,
        'stream': False,
    }
    code, body = req('/v1/chat/completions', token, payload, timeout=180)
    print('HTTP', code)
    try:
        j = json.loads(body)
        if 'error' in j:
            print('错误:', json.dumps(j['error'], ensure_ascii=False)[:400])
        else:
            print('真实后端 :', j.get('model'))
            msg = (j.get('choices') or [{}])[0].get('message', {})
            print('回复     :', (msg.get('content') or '').strip()[:300])
            print('usage    :', j.get('usage'))
    except Exception:
        print('原始:', body[:500])
    print()

    print('=== 3) new-api 日志（看是否命中渠道 12）===')
    import subprocess
    out = subprocess.run(['docker', 'logs', 'new-api', '--tail', '20'],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        if 'codely' in line.lower() or 'channel' in line.lower() or 'GIN' in line:
            print('  ', line.strip()[:160])


if __name__ == '__main__':
    main()
