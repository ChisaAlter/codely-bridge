#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codely 账号额度调度（每 5 分钟由 systemd timer 触发）
策略：优先用 PREFERRED（account-2），可用额度 < 1 积分时切到 FALLBACK（user-66040），
每日额度重置后自动切回 PREFERRED。两号都耗尽时保持现状等待重置，不互相抖动。
- 额度快照：代理内部口 127.0.0.1:8791 GET /quota?force=1（仅查当前账号）
- 切换：POST /account/switch?name=<账号>（免重启，自动重探模型）
- 耗尽标记存 .failover-state.json，有效期 = 当日窗口结束（每日 16:00 UTC / 北京 0 点）
"""
import json
import time
import urllib.request
from datetime import datetime, timezone

PROXY = "http://127.0.0.1:8791"
STATE_FILE = "/opt/codely-bridge/.failover-state.json"
LOG_FILE = "/opt/codely-bridge/failover.log"
PREFERRED = "account-2"
FALLBACK = "user-66040"
THRESHOLD = 100.0


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S") + "  " + msg
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def http_json(path, method="GET", timeout=40):
    req = urllib.request.Request(PROXY + path, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st):
    with open(STATE_FILE, "w") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def usable_quota(snap):
    """当前账号可用积分 = 每日赠送剩余 + 每日1万点giftCredits +  + 充值余额 + 订阅窗口剩余（兼容字段拼写）。"""
    d = snap.get("data") or {}
    usable = 0.0
    da = d.get("dailyAllowance") or {}
    if da.get("eligible") or da.get("has_active_policy"):
        usable += num(da.get("remaining_points"))
    g = d.get("giftCredits") or {}
    usable += num(g.get("remaining_points"))
    b = d.get("billing") or {}
    usable += num(b.get("effective_available_points"))
    for key in ("codingPlan", "coding_plan"):
        cp = d.get(key) or {}
        for w in (cp.get("windows") or []):
            for k, v in (w.items() if isinstance(w, dict) else []):
                if "remaining" in str(k).lower():
                    usable += num(v)
    return usable


def reset_epoch(snap):
    """当前账号每日窗口结束时间（epoch 秒），取不到则按下一个 16:00 UTC 估算。"""
    d = snap.get("data") or {}
    da = d.get("dailyAllowance") or {}
    pe = da.get("period_end_at")
    if pe:
        try:
            dt = datetime.fromisoformat(str(pe).replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            pass
    now = time.time()
    today4pm = datetime.now(timezone.utc).replace(hour=16, minute=0, second=0, microsecond=0).timestamp()
    return today4pm if now < today4pm else today4pm + 86400


def fmt_ts(ts):
    return time.strftime("%m-%d %H:%M", time.gmtime(ts)) + " UTC"


def main():
    try:
        snap = http_json("/quota?force=1")
    except Exception as e:
        log(f"[跳过] 额度接口不可达（代理可能没起）: {e}")
        return
    if not snap.get("ok"):
        log(f"[跳过] 额度接口返回异常: {json.dumps(snap)[:150]}")
        return

    data = snap.get("data") or {}
    cur = (data.get("account") or {}).get("name") or "(unknown)"
    usable = usable_quota(snap)
    reset = reset_epoch(snap)
    st = load_state()
    ex = st.setdefault("exhausted_until", {})

    if cur == PREFERRED:
        if usable < THRESHOLD:
            ex[PREFERRED] = reset
            st["last_action"] = f"{PREFERRED} 耗尽 -> 切 {FALLBACK}"
            save_state(st)
            log(f"{PREFERRED} 可用 {usable:.2f} 积分（<1），标记耗尽至 {fmt_ts(reset)}，切到 {FALLBACK}")
            try:
                r = http_json(f"/account/switch?name={FALLBACK}", method="POST")
                log(f"  切换结果: {json.dumps(r, ensure_ascii=False)[:150]}")
            except Exception as e:
                log(f"  切换失败: {e}")
        else:
            if PREFERRED in ex:
                ex.pop(PREFERRED, None)
                save_state(st)
            log(f"当前 {PREFERRED}（{usable:.2f} 积分），充足，无需调度")
        return

    # 当前在 FALLBACK 上
    pref_mark = ex.get(PREFERRED, 0)
    now = time.time()
    if now >= pref_mark and PREFERRED in ex:
        # 标记已过期：每日重置完成，切回首选
        log(f"{PREFERRED} 的耗尽标记已过期（每日额度已重置），切回首选账号")
        try:
            r = http_json(f"/account/switch?name={PREFERRED}", method="POST")
            log(f"  切换结果: {json.dumps(r, ensure_ascii=False)[:150]}")
            if r.get("ok"):
                ex.pop(PREFERRED, None)
                ex.pop(FALLBACK, None)
                save_state(st)
        except Exception as e:
            log(f"  切换失败: {e}")
        return
    if PREFERRED not in ex:
        # 没有任何耗尽标记却停在 FALLBACK（比如人工切过去的）——尊重现状
        log(f"当前 {cur}（{usable:.2f} 积分），{PREFERRED} 无耗尽标记，保持现状（人工切换优先）")
        return
    if usable < THRESHOLD:
        ex[FALLBACK] = reset
        save_state(st)
        log(f"{FALLBACK} 也耗尽（{usable:.2f}），{PREFERRED} 要到 {fmt_ts(pref_mark)} 才重置，两号都空，维持现状")
    else:
        log(f"当前 {cur}（{usable:.2f} 积分），{PREFERRED} 耗尽中（{fmt_ts(pref_mark)} 重置），正常候补中")


if __name__ == "__main__":
    main()
