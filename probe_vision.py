"""用一张纯色 PNG 测试模型的视觉能力是否真实可用。

用法: python3 probe_vision.py [模型名 ...]
不传参数则默认测 codely-vl 与 glm-5.3（对照，后者非视觉模型）。
"""
import base64
import json
import sqlite3
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib

DB = '/opt/new-api/data/one-api.db'
BASE = 'http://127.0.0.1:3390/v1'
SIZE = 64


def make_png(r, g, b):
    """构造一张纯色 PNG，返回 base64。"""
    raw = b''
    for _ in range(SIZE):
        raw += b'\x00' + bytes([r, g, b]) * SIZE

    def chunk(tag, data):
        c = tag + data
        return struct.pack('>I', len(data)) + c + struct.pack(
            '>I', zlib.crc32(c) & 0xffffffff)

    ihdr = struct.pack('>IIBBBBB', SIZE, SIZE, 8, 2, 0, 0, 0)
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', ihdr)
           + chunk(b'IDAT', zlib.compress(raw, 9))
           + chunk(b'IEND', b''))
    return base64.b64encode(png).decode()


def fetch_key():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute('SELECT "key" FROM tokens WHERE id=1')
    row = cur.fetchone()
    con.close()
    return row[0] if row else None


def ask(key, model, prompt, image_b64=None):
    if image_b64:
        content = [
            {'type': 'text', 'text': prompt},
            {'type': 'image_url',
             'image_url': {'url': 'data:image/png;base64,' + image_b64}},
        ]
    else:
        content = prompt
    body = json.dumps({
        'model': model,
        'messages': [{'role': 'user', 'content': content}],
        'max_tokens': 300,
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
        msg = j.get('choices', [{}])[0].get('message', {})
        return {'ok': True, 'text': (msg.get('content') or '').strip()[:180],
                'latency': time.time() - t0}
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode())
            msg = err.get('error', {}).get('message', str(e))
        except Exception:
            msg = str(e)
        return {'ok': False, 'code': e.code, 'msg': msg[:160]}
    except Exception as e:
        return {'ok': False, 'code': 'ERR', 'msg': str(e)[:160]}


def main():
    key = fetch_key()
    models = sys.argv[1:] or ['codely-vl', 'glm-5.3']
    img = make_png(220, 30, 30)
    print('测试图: %dx%d 纯红色 PNG (base64 %d 字节)\n' % (
        SIZE, SIZE, len(img)))
    for m in models:
        r = ask(key, m, '这张图是什么颜色？只回答颜色名称。', img)
        if r['ok']:
            print('  %-14s ✅ %.1fs  回答: %s' % (m, r['latency'], r['text']))
        else:
            print('  %-14s ❌ HTTP %s  %s' % (m, r['code'], r['msg']))


if __name__ == '__main__':
    main()
