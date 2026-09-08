"""轮换 new-api 对外 token 与 codely-gate 的内部 key。

用法: python3 rotate_keys.py [--dry-run]
改动前会自动备份数据库与 api-key.txt。
"""
import os
import secrets
import shutil
import sqlite3
import string
import sys
from datetime import datetime

DB = '/opt/new-api/data/one-api.db'
GATE_KEY_FILE = '/opt/codely-bridge/api-key.txt'
BACKUP_DIR = '/opt/backups'
ALPHABET = string.ascii_letters + string.digits
STAMP = datetime.now().strftime('%Y%m%d-%H%M%S')
DRY = '--dry-run' in sys.argv


def new_token(n=48):
    return ''.join(secrets.choice(ALPHABET) for _ in range(n))


def main():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    db_bak = os.path.join(BACKUP_DIR, 'one-api.db.bak-rotatekey-%s' % STAMP)
    shutil.copy2(DB, db_bak)
    print('已备份数据库 -> %s' % db_bak)

    if os.path.exists(GATE_KEY_FILE):
        kf_bak = os.path.join(BACKUP_DIR, 'api-key.txt.bak-%s' % STAMP)
        shutil.copy2(GATE_KEY_FILE, kf_bak)
        print('已备份网关 key -> %s' % kf_bak)

    new_api_token = new_token(48)
    new_gate_key = 'sk-codely-' + new_token(32)

    print()
    print('新 new-api token : %s (48 字符)' % new_api_token)
    print('新 codely-gate key: %s (42 字符)' % new_gate_key)

    if DRY:
        print()
        print('[dry-run] 未写入任何改动')
        return

    con = sqlite3.connect(DB)
    cur = con.cursor()

    cur.execute('UPDATE tokens SET "key"=? WHERE id=1', (new_api_token,))
    print()
    print('tokens.id=1 已更新 (影响 %d 行)' % cur.rowcount)

    cur.execute('UPDATE channels SET "key"=? WHERE id=12', (new_gate_key,))
    print('channels.id=12 已更新 (影响 %d 行)' % cur.rowcount)

    con.commit()

    cur.execute('SELECT id, name, length("key") FROM tokens WHERE id=1')
    print('校验 tokens.id=1 ->', cur.fetchone())
    cur.execute('SELECT id, name, length("key") FROM channels WHERE id=12')
    print('校验 channels.id=12 ->', cur.fetchone())
    con.close()

    with open(GATE_KEY_FILE, 'w') as f:
        f.write(new_gate_key)
    os.chmod(GATE_KEY_FILE, 0o600)
    print('已写入 %s (权限 600)' % GATE_KEY_FILE)


if __name__ == '__main__':
    main()
