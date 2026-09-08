import json, urllib.request

UP = "http://127.0.0.1:8791/v1/chat/completions"
HDR = {"Content-Type": "application/json", "Authorization": "Bearer probe"}

def try_model(name):
    body = json.dumps({
        "model": name,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 50, "stream": False,
    }).encode()
    try:
        req = urllib.request.Request(UP, data=body, headers=HDR, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            j = json.load(r)
            if "error" in j:
                return "ERROR: " + str(j["error"].get("message", j["error"]))[:400]
            return "OK -> backend=%s" % j.get("model")
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace")
        try:
            m = json.loads(txt).get("error", {}).get("message", txt)
        except Exception:
            m = txt
        return "HTTP %s: %s" % (e.code, m[:400])
    except Exception as e:
        return "EXC: %s" % str(e)[:300]

print("=== codely 上游直连：各种写法的 GLM-5.3 ===")
for n in ["GLM-5.3", "glm-5.3", "GLM-5.3-FLASH", "glm-5.3-flash", "codely-glm-5.3", "GLM5.3"]:
    print("  %-16s -> %s" % (n, try_model(n)))
