"""对 codely 上游逐个试未列出的模型名，判断白名单是否放行。

用法: python3 probe_alias.py [名字 ...]
直连 127.0.0.1:8791（绕过 new-api 的 abilities 索引），发最小请求看是否被接受。
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:8791/v1'

DEFAULT = [
    'GLM-5.3', 'glm-5.3', 'GLM-5.3-MAX', 'glm-5.3-max',
    'GLM-5.2', 'GLM-5.2-MAX', 'glm-5.2-max',
    'codely-glm-5.3', 'codely-glm53',
    'GLM-5.3-FLASH', 'codely-core',
]


def ask(model):
    body = json.dumps({
        'model': model,
        'messages': [{'role': 'user', 'content': 'hi'}],
        'max_tokens': 800,
        'stream': False,
    }).encode()
    req = urllib.request.Request(
        BASE + '/chat/completions',
        data=body,
        headers={'Content-Type': 'application/json',
                 'Authorization': 'Bearer probe'})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            j = json.loads(r.read().decode())
        msg = j.get('choices', [{}])[0].get('message', {})
        return {'ok': True, 'backend': j.get('model'),
                'text': (msg.get('content') or '').strip()[:50],
                'latency': time.time() - t0}
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode())
            m = err.get('error', {}).get('message', str(e))
        except Exception:
            m = (e.read().decode()[:160] if hasattr(e, 'read') else str(e))
        return {'ok': False, 'code': e.code, 'msg': m[:150]}
    except Exception as e:
        return {'ok': False, 'code': 'ERR', 'msg': str(e)[:150]}


def main():
    names = sys.argv[1:] or DEFAULT
    print('直连上游 %s，逐个试名字：\n' % BASE)
    for n in names:
        r = ask(n)
        if r['ok']:
            print('  ✅ %-20s → 后端 %-24s %.1fs  %s' % (
                n, r['backend'], r['latency'], r['text']))
        else:
            print('  ❌ %-20s HTTP %-5s %s' % (n, r['code'], r['msg']))


if __name__ == '__main__':
    main()
