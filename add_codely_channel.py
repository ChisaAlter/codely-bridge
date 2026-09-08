#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""往 new-api 插入 codely 渠道，并同步 abilities 索引。

两件事必须都做：
  channels  —— 渠道本身
  abilities —— 模型 → 渠道的索引，new-api 实际按这个路由
只插 channels 会导致所有请求 503 model_not_found。

幂等：同名渠道已存在则合并模型并重新同步 abilities，不会重复插入。

用法:
    python3 add_codely_channel.py [db_path]
"""
import sqlite3
import sys
import time

DB = sys.argv[1] if len(sys.argv) > 1 else '/opt/new-api/data/one-api.db'
KEY_FILE = '/opt/codely-bridge/api-key.txt'
TEMPLATE_CHANNEL = 'nvidia-k3'   # 借用它的字段默认值，保持风格一致

CHANNEL_NAME = 'codely'
BASE_URL = 'http://127.0.0.1:8790/v1'   # 经本机 auth-gate（校验 API Key）
TEST_MODEL = 'codely-core'
MODELS = 'codely-core,codely-flash,codely-air,codely-basic,codely-vl,KIMI-K3,GLM-5.3-FLASH'
REMARK = 'Codely / Tuanjie Cowork 额度，经本机 codely-proxy(8791) + auth-gate(8790) 转发'


def sync_abilities(cur, channel_id, models_csv, group):
    group = group or 'default'
    models = [m.strip() for m in (models_csv or '').split(',') if m.strip()]

    cur.execute('SELECT model FROM abilities WHERE channel_id=?', (channel_id,))
    have = {r[0] for r in cur.fetchall()}

    added = 0
    for m in models:
        if m in have:
            continue
        cur.execute(
            'INSERT INTO abilities ("group", model, channel_id, enabled, priority, weight, tag) '
            'VALUES (?,?,?,?,?,?,?)',
            (group, m, channel_id, 1, 0, 100, None))
        added += 1

    removed = 0
    for m in have - set(models):
        cur.execute('DELETE FROM abilities WHERE channel_id=? AND model=?', (channel_id, m))
        removed += 1

    print('  abilities: 新增 %d 条, 删除 %d 条, 最终 %d 条 (group=%s)'
          % (added, removed, len(models), group))


def main():
    with open(KEY_FILE, 'r', encoding='utf-8') as f:
        api_key = f.read().strip()
    if not api_key:
        sys.exit('API Key 为空，检查 ' + KEY_FILE)

    con = sqlite3.connect(DB)
    cur = con.cursor()

    cur.execute('SELECT id, name, base_url, models FROM channels WHERE name=?', (CHANNEL_NAME,))
    existing = cur.fetchone()

    if existing:
        channel_id = existing[0]
        old = [m.strip() for m in (existing[3] or '').split(',') if m.strip()]
        new = [m.strip() for m in MODELS.split(',') if m.strip()]
        merged = old + [m for m in new if m not in old]
        print('UPDATE: 渠道 %s 已存在 (id=%s)' % (CHANNEL_NAME, channel_id))
        print('  合并后 %d 个模型: %s' % (len(merged), ','.join(merged)))
        cur.execute('UPDATE channels SET models=?, base_url=?, "key"=? WHERE id=?',
                    (','.join(merged), BASE_URL, api_key, channel_id))
        con.commit()
        sync_abilities(cur, channel_id, ','.join(merged), 'default')
        con.commit()
    else:
        cur.execute('SELECT * FROM channels WHERE name=?', (TEMPLATE_CHANNEL,))
        row = cur.fetchone()
        cols = [d[0] for d in cur.description]
        tpl = dict(zip(cols, row)) if row else {}
        print("模板渠道 '%s': %s" % (TEMPLATE_CHANNEL, '已找到' if tpl else '不存在，用内置默认值'))

        now = int(time.time())
        group = tpl.get('group') or 'default'

        cur.execute("""
            INSERT INTO channels (
                type, "key", open_ai_organization, test_model, status, name, weight,
                created_time, test_time, response_time, base_url, other, balance,
                balance_updated_time, models, "group", used_quota, model_mapping,
                status_code_mapping, priority, auto_ban, other_info, tag, setting,
                param_override, header_override, remark, channel_info, settings
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            1,                                  # type=1 → OpenAI 兼容
            api_key,                            # auth-gate 的 API Key
            tpl.get('open_ai_organization'),
            TEST_MODEL,
            1,                                  # status=1 → 启用
            CHANNEL_NAME,
            tpl.get('weight') or 100,
            now, 0, 0,
            BASE_URL,
            tpl.get('other'),
            0, 0,
            MODELS,
            group,
            0, None, None,
            tpl.get('priority') or 0,
            tpl.get('auto_ban') if tpl.get('auto_ban') is not None else 1,
            None,
            tpl.get('tag'),
            tpl.get('setting'),
            None, None,
            REMARK,
            None,
            tpl.get('settings'),
        ))
        channel_id = cur.lastrowid
        con.commit()
        print('INSERTED: id=%s name=%s' % (channel_id, CHANNEL_NAME))
        sync_abilities(cur, channel_id, MODELS, group)
        con.commit()

    print('\n=== 当前渠道列表 ===')
    cur.execute('SELECT id, name, type, base_url, "group", status, test_model FROM channels ORDER BY id')
    for r in cur.fetchall():
        print('  id=%-3s %-14s type=%s status=%s group=%s test=%s' % (r[0], r[1], r[2], r[5], r[4], r[6]))
        print('      base_url: %s' % r[3])

    print('\n=== 该渠道的 abilities 索引 ===')
    cur.execute('SELECT "group", model, enabled, weight FROM abilities WHERE channel_id=?', (channel_id,))
    for r in cur.fetchall():
        print('  %-10s %-16s enabled=%s weight=%s' % r)

    con.close()
    print('\n完成。接下来需重启 new-api 刷新渠道缓存：docker restart new-api')


if __name__ == '__main__':
    main()
