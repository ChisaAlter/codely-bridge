import sqlite3
import sys

DB = '/opt/new-api/data/one-api.db'


def cols(cur, table):
    cur.execute('PRAGMA table_info(%s)' % table)
    return [r[1] for r in cur.fetchall()]


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    print('=== tokens 表字段 ===')
    tc = cols(cur, 'tokens')
    print(', '.join(tc))

    pick = ['id', 'name', 'status']
    for extra in ('remain_quota', 'unlimited_quota', 'expired_time', 'user_id'):
        if extra in tc:
            pick.append(extra)
    has_key = 'key' in tc
    if has_key:
        pick.append('key')

    cur.execute('SELECT %s FROM tokens ORDER BY id' % ','.join(pick))
    rows = cur.fetchall()
    print()
    print('=== 现有 token ===')
    for r in rows:
        d = dict(zip(pick, r))
        k = d.get('key', '')
        shown = (k[:8] + '...(' + str(len(k)) + '字符)') if k else '(空)'
        print('  id=%s name=%r status=%s quota=%s unlimited=%s key=%s' % (
            d.get('id'), d.get('name'), d.get('status'),
            d.get('remain_quota'), d.get('unlimited_quota'), shown))

    print()
    print('=== abilities 中的全部模型（按渠道） ===')
    cur.execute('SELECT channel_id, model FROM abilities ORDER BY channel_id, model')
    by_ch = {}
    for cid, m in cur.fetchall():
        by_ch.setdefault(cid, []).append(m)
    cur.execute('SELECT id, name FROM channels ORDER BY id')
    chname = dict(cur.fetchall())
    for cid in sorted(by_ch):
        print('  [%s] %s: %s' % (cid, chname.get(cid), ', '.join(by_ch[cid])))

    print()
    cur.execute('SELECT model FROM abilities')
    allm = sorted(set(r[0] for r in cur.fetchall()))
    print('=== 全部可用模型名 (%d) ===' % len(allm))
    print('\n'.join('  ' + m for m in allm))

    print()
    print('=== users（找管理员） ===')
    uc = cols(cur, 'users')
    upick = [c for c in ('id', 'username', 'role', 'status') if c in uc]
    if upick:
        cur.execute('SELECT %s FROM users ORDER BY id LIMIT 10' % ','.join(upick))
        for r in cur.fetchall():
            print('  ', r)

    con.close()


if __name__ == '__main__':
    main()
