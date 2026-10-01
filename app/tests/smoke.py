"""本题 API 冒烟脚本（在运行中的 web 容器内执行，访问本机服务）。

覆盖：健康检查、页面、最优求解 + 约化成本证据、审计重放原记录、
改载荷拒绝(409)、不可行证据、非法输入字段定位。任一断言失败即以
非零退出码结束。
"""

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"


def call(method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()
            return resp.status, (
                json.loads(raw) if "json" in resp.headers.get(
                    "Content-Type", "") else raw)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


SAMPLE = {
    "stations": [
        {"id": "S1", "balance": 6}, {"id": "S2", "balance": 4},
        {"id": "V1", "balance": 0}, {"id": "V2", "balance": 0},
        {"id": "D1", "balance": -3}, {"id": "D2", "balance": -7}],
    "pipes": [
        {"id": "p1", "from": "S1", "to": "V1", "lo": 1, "hi": 8, "cost": 2},
        {"id": "p2", "from": "S2", "to": "V1", "lo": 0, "hi": 5, "cost": 4},
        {"id": "p3", "from": "S2", "to": "V2", "lo": 1, "hi": 6, "cost": 1},
        {"id": "p4", "from": "V1", "to": "D1", "lo": 0, "hi": 4, "cost": 0},
        {"id": "p5", "from": "V1", "to": "D2", "lo": 0, "hi": 9, "cost": 3},
        {"id": "p6", "from": "V2", "to": "D2", "lo": 0, "hi": 7, "cost": 2},
        {"id": "p7", "from": "D1", "to": "D2", "lo": 0, "hi": 3,
         "cost": -1}],
}

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))
    print(("  PASS " if cond else "  FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


print(f"[smoke] target = {BASE}")

s, h = call("GET", "/health")
check("GET /health 200/ok", s == 200 and h.get("status") == "ok", str(h))

s, page = call("GET", "/")
check("GET / 页面", s == 200 and "最小费用流" in page)

s, b1 = call("POST", "/api/solve", SAMPLE, {"X-Audit-Id": "smoke-run-1"})
r1 = b1.get("result", {})
check("POST /api/solve 最优", s == 200 and r1.get("status") == "optimal",
      f"{s} {r1.get('status')}")
check("总成本为整数", isinstance(r1.get("total_cost"), int))
pi = r1.get("potentials", {})
rc_ok = all(
    a["reduced_cost"] >= 0 and
    a["reduced_cost"] == a["cost"] + pi[a["from"]] - pi[a["to"]]
    for e in r1.get("edges", []) for a in e["residual"])
check("正残量边约化成本全部 >= 0（最优性证据）", rc_ok)
node_ok = all(n["ok"] for n in r1.get("node_check", []))
check("逐站净供需复算全部通过", node_ok)

s, b2 = call("POST", "/api/solve", SAMPLE, {"X-Audit-Id": "smoke-run-1"})
check("同标识同载荷重放原记录",
      s == 200 and b2.get("replayed") is True and
      b2.get("result") == r1, str(s))

changed = json.loads(json.dumps(SAMPLE))
changed["pipes"][0]["cost"] = 42
s, b3 = call("POST", "/api/solve", changed, {"X-Audit-Id": "smoke-run-1"})
check("同标识改载荷被拒绝 409", s == 409 and "不同载荷" in b3.get("error", ""),
      str(s))

bad_cut = {"stations": [{"id": "S", "balance": 5},
                        {"id": "T", "balance": -5}],
           "pipes": [{"id": "x", "from": "S", "to": "T",
                      "lo": 0, "hi": 2, "cost": 1}]}
s, b4 = call("POST", "/api/solve", bad_cut)
check("无可行流返回未满足需求与可达集",
      s == 200 and b4.get("status") == "infeasible" and
      b4["unmet_demand"][0]["station"] == "T" and
      b4["unmet_demand"][0]["unsatisfied"] == 3 and
      "S" in b4["reachable_from_source"], str(b4)[:200])

bad_input = {"stations": [{"id": "S", "balance": 1.5},
                          {"id": "T", "balance": -1}], "pipes": []}
s, b5 = call("POST", "/api/solve", bad_input)
check("非法输入定位字段", s == 400 and b5.get("loc") == "stations[0].balance",
      str(b5))

# ---- 超过 JS/常见前端安全整数范围（2^53）的合法大液路，无损端到端 ----
BIG = 10 ** 18            # 系统允许的量级
BIG_COST = 10 ** 12
big_payload = {
    "stations": [
        {"id": "S", "balance": BIG},
        {"id": "V", "balance": 0},
        {"id": "T", "balance": -BIG}],
    "pipes": [
        {"id": "cheap", "from": "S", "to": "V", "lo": 0,
         "hi": BIG, "cost": BIG_COST},
        {"id": "lo_pipe", "from": "V", "to": "T", "lo": BIG // 2,
         "hi": BIG, "cost": 3},
        {"id": "direct", "from": "S", "to": "T", "lo": 0,
         "hi": BIG, "cost": BIG_COST + 10}],
}
s, bb = call("POST", "/api/solve", big_payload, {"X-Audit-Id": "big-run-1"})
br = bb.get("result", {})
check("超大整数网络求最优", s == 200 and br.get("status") == "optimal",
      f"{s} {br.get('status')}")
if br.get("status") == "optimal":
    flows = {f["id"]: f["flow"] for f in br["flows"]}
    # Python json 本身任意精度；断言类型与精确值，杜绝任何中途浮点化
    check("大流量为精确 int", all(isinstance(f, int) for f in flows.values()))
    # 最便宜路由：direct 单价贵 1，故全部走 S->V->T；下界钉死 lo_pipe=5e17
    expect_cost = BIG * BIG_COST + BIG * 3
    check("最优流路由正确（全走便宜路径，下界满足）",
          flows["cheap"] == BIG and flows["lo_pipe"] == BIG
          and flows["direct"] == 0, str(flows))
    check("总成本精确等于 10^30 + 3·10^18（无精度损失）",
          br["total_cost"] == expect_cost and
          isinstance(br["total_cost"], int), str(br["total_cost"]))
    # 逐边费用贡献复算
    contrib_ok = all(
        e["cost_contribution"] == flows[e["id"]] * e["cost"]
        and isinstance(e["cost_contribution"], int)
        for e in br["edges"])
    check("逐边费用贡献可复算且为精确整数", contrib_ok)
    # 站点净流出复算
    net = {n["station"]: n["outflow"] - n["inflow"] for n in br["node_check"]}
    bal = {x["id"]: x["balance"] for x in big_payload["stations"]}
    check("各站净流出精确复算", net == bal and all(n["ok"]
          for n in br["node_check"]), f"{net} vs {bal}")
    # 势 + 正残量边约化成本复算（全部 >= 0）
    pi = br["potentials"]
    rc_ok = all(isinstance(a["reduced_cost"], int) and
                a["reduced_cost"] >= 0 and
                a["reduced_cost"] ==
                a["cost"] + pi[a["from"]] - pi[a["to"]]
                for e in br["edges"] for a in e["residual"])
    check("大整数势与正残量边约化成本可复算（>=0）", rc_ok)

    # 同一审计标识、数值等价但写法不同的重传（大整数改以严格十进制
    # 字符串上送，模拟页面 BigInt 无损通道）：必须稳定取回原记录
    equiv = json.loads(json.dumps(big_payload))
    equiv["pipes"][0]["hi"] = str(BIG)
    equiv["stations"][0]["balance"] = str(BIG)
    s, be = call("POST", "/api/solve", equiv, {"X-Audit-Id": "big-run-1"})
    check("数值等价重传命中原记录（replayed，记录逐字节一致）",
          s == 200 and be.get("replayed") is True and
          be.get("result") == br and be.get("payload_fingerprint")
          == bb.get("payload_fingerprint"), str(s))

    # 同标识改载荷仍必须 409 拒绝
    tampered = json.loads(json.dumps(big_payload))
    tampered["pipes"][2]["cost"] = BIG_COST - 5
    s, bc = call("POST", "/api/solve", tampered, {"X-Audit-Id": "big-run-1"})
    check("大整数场景同标识改载荷仍拒绝 409", s == 409 and
          "不同载荷" in bc.get("error", ""), str(s))

# ---- 非法边界/非法整数语义保持 ----
bad_sci = {"stations": [{"id": "S", "balance": "1e18"},
                        {"id": "T", "balance": "-1e18"}], "pipes": []}
s, b6 = call("POST", "/api/solve", bad_sci)
check("科学计数字符串按非法整数拒绝",
      s == 400 and b6.get("loc") == "stations[0].balance", str(b6))
bad_bound = {"stations": [{"id": "S", "balance": 1},
                          {"id": "T", "balance": -1}],
             "pipes": [{"id": "x", "from": "S", "to": "T",
                        "lo": 5, "hi": 4, "cost": 1}]}
s, b7 = call("POST", "/api/solve", bad_bound)
check("hi < lo 非法边界定位 pipes[0].hi",
      s == 400 and b7.get("loc") == "pipes[0].hi", str(b7))

failed = [n for n, ok, _ in CHECKS if not ok]
print(f"[smoke] {len(CHECKS) - len(failed)}/{len(CHECKS)} passed")
sys.exit(1 if failed else 0)
