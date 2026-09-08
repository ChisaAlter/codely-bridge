"""逐个探测 new-api 里所有模型的真实可用性。

用法: python3 probe_models.py
从 tokens 表取 id=1 的 key，本地调 127.0.0.1:3390，输出每个模型的真实后端与延迟。
"""
import json
import sqlite3
import time
import urllib.error
import urllib.request

DB = '/opt/new-api/data/one-api.db'
BASE = 'http://127.0.0.1:3390/v1'

# 推理模型需要更大的 max_tokens，否则 token 全被 reasoning 吃掉
BIG_TOKENS = {
    'codely-core', 'codely-flash', 'codely-air', 'codely-basic', 'codely-vl',
    'KIMI-K3', 'GLM-5.3-FLASH',
}


def fetch_key():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute('SELECT "key" FROM tokens WHERE id=1')
    row = cur.fetchone()
    con.close()
    return row[0] if row else None


def fetch_models(key):
    req = urllib.request.Request(
        BASE + '/models', headers={'Authorization': 'Bearer ' + key})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    return [m['id'] for m in data.get('data', [])]


def probe(key, model):
    mt = 2000 if model in BIG_TOKENS else 400
    body = json.dumps({
        'model': model,
        'messages': [{'role': 'user', 'content': 'hi'}],
        'max_tokens': mt,
        'stream': False,
    }).encode()
    req = urllib.request.Request(
        BASE + '/chat/completions',
        data=body,
        headers={'Authorization': 'Bearer ' + key,
                 'Content-Type': 'application/json'})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=150) as r:
            j = json.loads(r.read().decode())
        dt = time.time() - t0
        msg = j.get('choices', [{}])[0].get('message', {})
        content = (msg.get('content') or '').strip()
        usage = j.get('usage') or {}
        det = (usage.get('completion_tokens_details') or {})
        return {
            'ok': True,
            'backend': j.get('model'),
            'latency': dt,
            'content': content[:40] or '(空)',
            'reasoning': det.get('reasoning_tokens', 0),
            'total': usage.get('total_tokens', 0),
        }
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode())
            msg = err.get('error', {}).get('message', str(err))
        except Exception:
            msg = str(e)
        return {'ok': False, 'code': e.code, 'msg': msg[:110],
                'latency': time.time() - t0}
    except Exception as e:
        return {'ok': False, 'code': 'ERR', 'msg': str(e)[:110],
                'latency': time.time() - t0}


def main():
    key = fetch_key()
    if not key:
        print('无法读取 token')
        return
    models = fetch_models(key)
    print('共 %d 个模型，开始逐个探测...\n' % len(models))
    ok, bad = [], []
    for m in models:
        r = probe(key, m)
        if r['ok']:
            ok.append((m, r))
            print('  ✅ %-28s → %-24s %5.1fs  %s' % (
                m, r['backend'], r['latency'], r['content']))
        else:
            bad.append((m, r))
            print('  ❌ %-28s HTTP %-5s %s' % (m, r['code'], r['msg']))
    print('\n=== 汇总 ===')
    print('可用 %d / 共 %d' % (len(ok), len(models)))
    if bad:
        print('\n不可用:')
        for m, r in bad:
            print('  - %s : %s' % (m, r['msg']))


if __name__ == '__main__':
    main()
