import json, urllib.request, time

TOKEN = "ZR2m8lycVOVGfLlqaUtnzvWClPGLNJkB6G0kyamxlUYHi79V"

print("=== ① 上游 8791 /v1/models 声明的 max_model_len ===")
try:
    with urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8791/v1/models"), timeout=30) as r:
        j = json.load(r)
    for m in j.get("data", []):
        print("  %-16s max_model_len=%s" % (m["id"], m.get("max_model_len")))
except Exception as e:
    print("  fetch error:", e)

print("")
print("=== ② 经我的反代(127.0.0.1:3389) 发一个 >128K token 请求给 codely-core ===")
base = "这是一段用于测试上下文长度的中文文本，包含鲲鹏展翅九万里和量子纠缠态叠加原理以避免被BPE压缩。"
big = (base + "\n") * 5000   # ~300K 字符，约 180K+ tokens，稳超 128K
print("  prompt 字符数: %d" % len(big))
payload = {
    "model": "codely-core",
    "messages": [{"role": "user", "content": "只回复两个字：收到。" + big}],
    "max_tokens": 20, "stream": False,
}
body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
print("  POST 字节数: %d" % len(body))
t0 = time.time()
req = urllib.request.Request("http://127.0.0.1:3389/v1/chat/completions",
    data=body, headers={"Content-Type": "application/json", "Authorization": "Bearer " + TOKEN}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=540) as r:
        j2 = json.load(r)
    dt = time.time() - t0
    print("  => HTTP 200, 耗时 %.1fs" % dt)
    print("  返回 model :", j2.get("model"))
    u = j2.get("usage") or {}
    print("  usage      : prompt_tokens=%s completion_tokens=%s" % (u.get("prompt_tokens"), u.get("completion_tokens")))
    print("  回答       :", (j2.get("choices", [{}])[0].get("message", {}).get("content") or "")[:40])
except urllib.error.HTTPError as e:
    dt = time.time() - t0
    txt = e.read().decode("utf-8", "replace")
    print("  => HTTP %s, 耗时 %.1fs" % (e.code, dt))
    print("  错误: %s" % txt[:400])
except Exception as e:
    print("  => 异常(可能超时): %s" % str(e)[:200])
