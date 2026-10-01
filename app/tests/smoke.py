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

# 测试侧也按任意精度整数解析，避免在客户端核对时先丢精度。
def _parse_exact(text):
    return json.loads(text, parse_int=int)


def call(method, path, body=None, headers=None, raw=None):
    data = raw if raw is not None else (
        json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_text = resp.read().decode()
            return resp.status, (
                _parse_exact(raw_text) if "json" in resp.headers.get(
                    "Content-Type", "") else raw_text)
    except urllib.error.HTTPError as e:
        return e.code, _parse_exact(e.read().decode())


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

# ------------------------------------------------------------ 超大整数液路
BIG = 10 ** 18
# 超过 Number.MAX_SAFE_INTEGER(2^53-1)：页面以十进制字符串承载
big_str = {
    "stations": [{"id": "S", "balance": str(BIG)},
                 {"id": "T", "balance": f"-{BIG}"}],
    "pipes": [
        {"id": "cheap", "from": "S", "to": "T",
         "lo": "0", "hi": str(BIG // 2), "cost": "3"},
        {"id": "pricey", "from": "S", "to": "T",
         "lo": "0", "hi": str(BIG), "cost": str(BIG)}]}
s, b6 = call("POST", "/api/solve", big_str, {"X-Audit-Id": "smoke-big-1"})
r6 = b6.get("result", {})
expected_cost = BIG // 2 * 3 + (BIG - BIG // 2) * BIG
check("超大整数液路取得最优",
      s == 200 and r6.get("status") == "optimal" and
      isinstance(r6.get("total_cost"), int),
      f"{s} {r6.get('status')}")
check("精确总成本（10^36 量级，无损）",
      r6.get("total_cost") == expected_cost, str(r6.get("total_cost")))

# 逐边复算：流量在界内、费用贡献之和 = 总成本、站点净流出 = balance
flows6 = {f["id"]: f["flow"] for f in r6.get("flows", [])}
recomputed = 0
detail_ok = True
for p in big_str["pipes"]:
    f = flows6.get(p["id"])
    if not (isinstance(f, int) and int(p["lo"]) <= f <= int(p["hi"])):
        detail_ok = False
    recomputed += f * int(p["cost"])
edge_sum = sum(e["cost_contribution"] for e in r6.get("edges", []))
check("逐边流量在界内且费用贡献可复算",
      detail_ok and recomputed == expected_cost and edge_sum == expected_cost)
check("超大网络逐站净流出复算通过",
      all(n.get("ok") and isinstance(n.get("net_out"), int)
          for n in r6.get("node_check", [])))
pi6 = r6.get("potentials", {})
big_rc_ok = all(
    isinstance(a["reduced_cost"], int) and
    a["reduced_cost"] >= 0 and
    a["reduced_cost"] == a["cost"] + pi6[a["from"]] - pi6[a["to"]]
    for e in r6.get("edges", []) for a in e["residual"])
check("超大网络正残量边约化成本为精确整数且 >= 0", big_rc_ok)

# 同标识以数值等价的 JSON 大整数 token 重传 -> 稳定取回原记录
big_token = {
    "stations": [{"id": "S", "balance": BIG},
                 {"id": "T", "balance": -BIG}],
    "pipes": [
        {"id": "cheap", "from": "S", "to": "T",
         "lo": 0, "hi": BIG // 2, "cost": 3},
        {"id": "pricey", "from": "S", "to": "T",
         "lo": 0, "hi": BIG, "cost": BIG}]}
s, b7 = call("POST", "/api/solve", big_token, {"X-Audit-Id": "smoke-big-1"})
check("超大整数数值等价重放原记录",
      s == 200 and b7.get("replayed") is True and
      b7.get("result") == r6 and
      b7.get("payload_fingerprint") == b6.get("payload_fingerprint"), str(s))

# 同标识改载荷（大整数）仍 409
big_changed = json.loads(json.dumps(big_token))
big_changed["pipes"][0]["cost"] = 4
s, b8 = call("POST", "/api/solve", big_changed,
             {"X-Audit-Id": "smoke-big-1"})
check("超大整数改载荷复用拒绝 409", s == 409, str(s))

# 字符串浮点记法仍按非法输入拒绝
s, b9 = call("POST", "/api/solve",
             {"stations": [{"id": "S", "balance": "1.5"},
                           {"id": "T", "balance": -1}], "pipes": []})
check("字符串浮点仍非法并定位字段",
      s == 400 and b9.get("loc") == "stations[0].balance", str(b9))

# 超大整数无可行流：证据仍精确
s, b10 = call("POST", "/api/solve",
              {"stations": [{"id": "S", "balance": BIG},
                            {"id": "T", "balance": -BIG}],
               "pipes": [{"id": "x", "from": "S", "to": "T",
                          "lo": 0, "hi": 2, "cost": 1}]})
check("超大整数不可行证据精确",
      s == 200 and b10.get("status") == "infeasible" and
      b10["unmet_demand"][0]["unsatisfied"] == BIG - 2 and
      isinstance(b10["unmet_demand"][0]["unsatisfied"], int), str(b10)[:200])

failed = [n for n, ok, _ in CHECKS if not ok]
print(f"[smoke] {len(CHECKS) - len(failed)}/{len(CHECKS)} passed")
sys.exit(1 if failed else 0)
