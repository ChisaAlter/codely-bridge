import json, urllib.request

UP = "http://127.0.0.1:8791/v1/chat/completions"
HDR = {"Content-Type": "application/json", "Authorization": "Bearer probe"}

body = json.dumps({
    "model": "codely-core",
    "messages": [{"role": "user", "content": "你好，请用一句话说明你的模型版本。"}],
    "max_tokens": 200, "stream": False,
}).encode()
req = urllib.request.Request(UP, data=body, headers=HDR, method="POST")
with urllib.request.urlopen(req, timeout=120) as r:
    j = json.load(r)

print("===== codely-core 完整响应元数据 =====")
print("顶层字段:", list(j.keys()))
print("model              :", j.get("model"))
print("system_fingerprint :", j.get("system_fingerprint"))
print("id                 :", j.get("id"))
print("object             :", j.get("object"))
u = j.get("usage") or {}
print("usage              :", json.dumps(u, ensure_ascii=False))
print("choices[0].finish_reason:", j.get("choices", [{}])[0].get("finish_reason"))
print("回答:", (j.get("choices", [{}])[0].get("message", {}).get("content") or "")[:120])
