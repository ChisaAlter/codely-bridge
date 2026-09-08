import json, urllib.request, base64

UP = "http://127.0.0.1:8791/v1/chat/completions"
HDR = {"Content-Type": "application/json", "Authorization": "Bearer probe"}

# 1x1 红色 PNG
RED_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

def call(payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(UP, data=body, headers=HDR, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)

print("===== 1) codely-core 真实后端 + 是否推理 =====")
r = call({
    "model": "codely-core",
    "messages": [{"role": "user", "content": "所有A都是B，所有B都是C。那么所有A都是C吗？请逐步推理。"}],
    "max_tokens": 2000, "stream": False,
})
u = r.get("usage") or {}
det = (u.get("completion_tokens_details") or {})
print("  返回 model 字段 :", r.get("model"))
print("  推理 token (reasoning_tokens):", det.get("reasoning_tokens"))
print("  输出 token      :", u.get("completion_tokens"))
print("  回答前60字      :", (r.get("choices",[{}])[0].get("message",{}).get("content") or "")[:60].replace("\n"," "))

print("")
print("===== 2) codely-core 视觉能力（喂一张红色图） =====")
r2 = call({
    "model": "codely-core",
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "这张图是什么颜色？只回答颜色。"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(RED_PNG).decode()}},
        ],
    }],
    "max_tokens": 200, "stream": False,
})
print("  视觉回答        :", (r2.get("choices",[{}])[0].get("message",{}).get("content") or "")[:40].replace("\n"," "))
