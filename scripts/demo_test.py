"""Demo 脚本测试 - 按视频流程生成测试数据"""
import urllib.request, json, base64, time, os

URL = "http://106.13.186.155:7078"

# 期刊阅览区照片
PHOTO_PATH = r"C:\Users\Administrator\Desktop\Hackathon\qk.jpg"

# ===== Demo 流程测试用例 =====
DEMO_STEPS = [
    # (镜头名称, 输入内容, 功能点, 时间预算)
    ("场景2-身份识别", "你是谁", "Guide Agent 意图识别 + Search Agent 知识检索", "8-22s"),
    ("场景3-借阅问答", "借阅规则是什么", "RAG混合检索 + Step 3.7 Flash生成", "22-38s"),
    ("场景4-拍照识别", "__PHOTO__", "Step 3.7 Flash 多模态识别", "38-55s"),
    ("场景5-路径导航", "怎么去期刊阅览室", "Planning Agent A*路径规划", "55-70s"),
    ("场景6-开放时间", "周末开门吗", "Verify Agent 事实校验", "70-85s"),
]

# ===== 附加深度测试 =====
EXTRA_TESTS = [
    ("拍照追问", "期刊阅览室在几楼"),
    ("导航追问", "从大厅怎么去"),
    ("规则细节", "一次可以借几本书"),
    ("超期处理", "图书超期了怎么办"),
    ("续借流程", "怎么续借图书"),
    ("新生开通", "新生怎么开通借阅权限"),
    ("设施查询", "怎么预约自习座位"),
    ("WiFi查询", "图书馆WiFi密码多少"),
    ("找书方法", "怎么找一本书的位置"),
    ("索书号说明", "索书号怎么看"),
]


def test_chat(message, label=""):
    """文本对话测试"""
    data = json.dumps({"message": message}).encode()
    req = urllib.request.Request(
        f"{URL}/chat", data=data,
        headers={"Content-Type": "application/json"}
    )
    t0 = time.time()
    try:
        r = urllib.request.urlopen(req, timeout=60)
        t1 = time.time()
        result = json.loads(r.read())
        return {
            "label": label,
            "input": message,
            "intent": result.get("intent", "?"),
            "response": result.get("response", ""),
            "server_time_s": round(result.get("processing_time_ms", 0) / 1000, 1),
            "client_time_s": round(t1 - t0, 1),
            "ok": len(result.get("response", "")) > 20,
        }
    except Exception as e:
        return {
            "label": label, "input": message,
            "intent": "ERROR", "response": str(e),
            "server_time_s": 0, "client_time_s": 0, "ok": False,
        }


def test_photo(photo_path, label=""):
    """图片上传测试"""
    if not os.path.exists(photo_path):
        return {"label": label, "input": photo_path, "response": "FILE_NOT_FOUND", "ok": False}

    with open(photo_path, "rb") as f:
        img_data = f.read()

    import io
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="qk.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode() + img_data + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="session_id"\r\n\r\n'
        f"demo_test\r\n"
        f"--{boundary}--\r\n"
    ).encode()

    req = urllib.request.Request(
        f"{URL}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    t0 = time.time()
    try:
        r = urllib.request.urlopen(req, timeout=60)
        t1 = time.time()
        result = json.loads(r.read())
        return {
            "label": label,
            "input": f"📷 {os.path.basename(photo_path)}",
            "intent": result.get("intent", "?"),
            "response": result.get("response", ""),
            "target_location": result.get("target_location", ""),
            "server_time_s": round(result.get("processing_time_ms", 0) / 1000, 1),
            "client_time_s": round(t1 - t0, 1),
            "ok": len(result.get("response", "")) > 20,
        }
    except Exception as e:
        return {
            "label": label, "input": photo_path,
            "intent": "ERROR", "response": str(e),
            "ok": False,
        }


# ===== 开始测试 =====
print("=" * 70)
print("  吉小图 Demo 视频测试数据生成")
print(f"  服务: {URL}")
print(f"  照片: {PHOTO_PATH}")
print("=" * 70)

results = []

# [1] Demo 流程
print("\n" + "=" * 50)
print("  Part 1: Demo 视频流程")
print("=" * 50)

for name, msg, feature, timing in DEMO_STEPS:
    print(f"\n{'─' * 40}")
    print(f"【{name}】{feature} ({timing})")
    print(f"{'─' * 40}")

    if msg == "__PHOTO__":
        r = test_photo(PHOTO_PATH, name)
        print(f"  输入: 📷 {os.path.basename(PHOTO_PATH)}")
    else:
        r = test_chat(msg, name)
        print(f"  输入: {msg}")

    status = "✅" if r["ok"] else "❌"
    print(f"  意图: {r.get('intent', '?')} | 耗时: {r.get('server_time_s', 0)}s | {status}")
    print(f"  回复: {r.get('response', '')[:200]}")
    if r.get("target_location"):
        print(f"  位置: {r['target_location']}")
    results.append(r)
    time.sleep(2)

# [2] 附加测试
print("\n" + "=" * 50)
print("  Part 2: 附加深度测试")
print("=" * 50)

for name, msg in EXTRA_TESTS:
    print(f"\n{'─' * 40}")
    print(f"【{name}】")
    r = test_chat(msg, name)
    print(f"  输入: {msg}")
    status = "✅" if r["ok"] else "❌"
    print(f"  意图: {r.get('intent', '?')} | 耗时: {r.get('server_time_s', 0)}s | {status}")
    print(f"  回复: {r.get('response', '')[:200]}")
    results.append(r)
    time.sleep(2)

# [3] 统计
print("\n" + "=" * 70)
demo_ok = sum(1 for r in results[:5] if r["ok"])
extra_ok = sum(1 for r in results[5:] if r["ok"])
total = len(results)
print(f"  Demo流程: {demo_ok}/5 通过")
print(f"  附加测试: {extra_ok}/{len(EXTRA_TESTS)} 通过")
print(f"  总计: {demo_ok + extra_ok}/{total} 通过")
avg = sum(r.get("server_time_s", 0) for r in results if r["server_time_s"] > 0) / max(total, 1)
print(f"  平均耗时: {avg:.1f}s")
print("=" * 70)

# [4] 输出测试数据 Markdown
print("\n生成测试数据 Markdown...\n")
for r in results:
    status = "✅" if r["ok"] else "❌"
    print(f"### {status} {r['label']}")
    print(f"- **输入**: {r['input']}")
    if r.get("intent"):
        print(f"- **意图**: {r['intent']} | **耗时**: {r.get('server_time_s', 0)}s")
    if r.get("target_location"):
        print(f"- **识别位置**: {r['target_location']}")
    print(f"- **回复**: {r['response'][:300]}")
    print()
