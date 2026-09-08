#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读检查 new-api 的 channels / abilities，为插入新渠道做准备。

只做 SELECT，不修改任何数据。key 字段脱敏显示。
"""
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else '/opt/new-api/data/one-api.db'


def mask(s, n=6):
    if s is None:
        return 'NULL'
    s = str(s).split('\n')[0]
    return s[:n] + '...' + ('(%d 字符)' % len(s) if len(s) > n else '')


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    print('=== channels 表列 ===')
    cur.execute('PRAGMA table_info(channels)')
    cols = [r[1] for r in cur.fetchall()]
    print(', '.join(cols))
    print()

    print('=== 现有渠道（key 已脱敏）===')
    cur.execute('SELECT id, name, type, base_url, "group", models, status, weight, priority FROM channels ORDER BY id')
    rows = cur.fetchall()
    print('%-4s %-22s %-5s %-38s %-10s %-4s %-5s' % ('id', 'name', 'type', 'base_url', 'group', 'stat', 'prio'))
    print('-' * 110)
    for r in rows:
        cid, name, typ, base, grp, models, status, weight, prio = r
        models_s = (models or '')[:26] + ('…' if models and len(models) > 26 else '')
        print('%-4s %-22s %-5s %-38s %-10s %-4s %-5s' % (cid, name, typ, (base or '')[:38], grp, status, prio))
        print('      models: %s' % models_s)
    print()

    print('=== abilities 表列 ===')
    cur.execute('PRAGMA table_info(abilities)')
    print(', '.join([r[1] for r in cur.fetchall()]))
    print()

    print('=== abilities 现有分组与条目数 ===')
    cur.execute('SELECT "group", COUNT(*), COUNT(DISTINCT model) FROM abilities GROUP BY "group"')
    for r in cur.fetchall():
        print('  group=%-16s 条目=%-5s 模型数=%s' % r)
    print()

    print('=== 现有渠道用到的 weight / priority 取值（保持一致）===')
    cur.execute('SELECT DISTINCT weight, priority FROM channels')
    for r in cur.fetchall():
        print('  weight=%s priority=%s' % r)
    print()

    # 冲突检查：待加入的模型名是否已被别的渠道占用
    want = ['codely-core', 'codely-flash', 'codely-air', 'codely-basic', 'codely-vl',
            'KIMI-K3', 'GLM-5.3-FLASH']
    print('=== 模型名冲突检查（待接入 vs 已占用）===')
    cur.execute('SELECT model, channel_id, "group" FROM abilities')
    ab = cur.fetchall()
    for m in want:
        hits = [a for a in ab if a[0] == m]
        if hits:
            print('  ⚠️  %-16s 已被占用: %s' % (m, hits))
        else:
            print('  ✅ %-16s 无冲突' % m)
    print()

    print('=== 库文件大小 / 表行数 ===')
    cur.execute('SELECT COUNT(*) FROM channels')
    print('  channels  :', cur.fetchone()[0])
    cur.execute('SELECT COUNT(*) FROM abilities')
    print('  abilities :', cur.fetchone()[0])

    con.close()


if __name__ == '__main__':
    main()
