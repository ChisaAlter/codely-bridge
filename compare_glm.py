"""横向对比 GLM 系列各模型的推理质量与开销。

用法: python3 compare_glm.py
经 new-api (127.0.0.1:3390) 调用，发同一组题，对比延迟、推理 token 与答案。
"""
import json
import re
import sqlite3
import time
import urllib.error
import urllib.request

DB = '/opt/new-api/data/one-api.db'
BASE = 'http://127.0.0.1:3390/v1'

MODELS = [
    'glm-5', 'glm-5.1', 'glm-5.3', 'glm-5.3-0731-oc',
    'GLM-5.3-FLASH', 'codely-core',
]
BIG = {'codely-core', 'GLM-5.3-FLASH'}

QUESTIONS = [
    ('数学', '一个水池，甲管单独开3小时注满，乙管单独开6小时注满。'
             '两管同时开，几小时注满？只回答数字。', r'2'),
    ('逻辑', '如果所有的A都是B，所有的B都是C，那么所有的A都是C吗？'
             '只回答"是"或"否"。', r'是'),
    ('常识', '中国的首都是哪个城市？只回答城市名。', r'北京'),
]


def fetch_key():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute('SELECT "key" FROM tokens WHERE id=1')
    row = cur.fetchone()
    con.close()
    return row[0]


def ask(key, model, prompt, max_tokens=1500):
    body = json.dumps({
        'model': model,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': max_tokens,
        'stream': False,
    }).encode()
    req = urllib.request.Request(
        BASE + '/chat/completions', data=body,
        headers={'Authorization': 'Bearer ' + key,
                 'Content-Type': 'application/json'})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            j = json.loads(r.read().decode())
        dt = time.time() - t0
        msg = j.get('choices', [{}])[0].get('message', {})
        usage = j.get('usage') or {}
        det = usage.get('completion_tokens_details') or {}
        return {'ok': True, 'backend': j.get('model'), 'latency': dt,
                'text': (msg.get('content') or '').strip(),
                'reasoning': det.get('reasoning_tokens', 0)}
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode())
            m = err.get('error', {}).get('message', str(e))
        except Exception:
            m = str(e)
        return {'ok': False, 'msg': m[:80], 'latency': time.time() - t0}
    except Exception as e:
        return {'ok': False, 'msg': str(e)[:80], 'latency': time.time() - t0}


def main():
    key = fetch_key()
    print('%-18s %-22s %-8s %-8s %s' % ('模型', '真实后端', '耗时', '推理tok', '三题结果'))
    print('-' * 88)
    for m in MODELS:
        results = []
        backend = ''
        total_t = 0.0
        total_r = 0
        for name, q, expect in QUESTIONS:
            r = ask(key, m, q, 2500 if m in BIG else 800)
            if not r['ok']:
                results.append('ERR')
                total_t += r['latency']
                continue
            backend = r['backend']
            total_t += r['latency']
            total_r += r['reasoning']
            hit = re.search(expect, r['text']) is not None
            results.append(('✓' if hit else '✗') + name)
        print('%-18s %-22s %-8s %-8s %s' % (
            m, backend or '-', '%.1fs' % total_t, total_r, ' '.join(results)))


if __name__ == '__main__':
    main()
