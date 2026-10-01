"""任意精度整数 JSON 读写（仅标准库）。

约定：接口中的整数字面量（供需、上下界、单位成本，以及返回的总成本、
势、约化成本等，可达 10^18 乃至乘积量级 10^30）必须全程保持 ``int``，
绝不经过 float。

- 读：显式以 ``parse_int=int`` 解析（标准库 ``json`` 对整数 token 本就用
  ``int``，这里固化该约定并加上字面量位数上限，防止畸形输入构造超大整数）。
  浮点 token 仍解析为 float，交由字段级校验拒绝，从而保留精确到字段路径
  （如 ``pipes[3].hi``）的错误定位语义。
- 写：``json.dumps`` 对 Python int 直接输出完整十进制定点字面量
  （无指数、无精度损失），故响应中的总成本与逐边证据天然无损。
- 页面侧（JS Number 只有 53 位尾数）无法在 JSON 中无损承载超大整数，
  故超出安全范围的数以十进制 *字符串* 承载，由 solver 在字段校验时按
  数值等价接受（见 solver._require_int / canonicalize_payload）。
"""

from __future__ import annotations

import json
from typing import Any

# 合法字段上限为 1e18，费用与势的中间量不超过 ~1e20；128 位数字的字面量
# 只可能是畸形/滥用输入，直接在解析层拒绝，避免超大整数构造造成资源消耗。
_MAX_INT_DIGITS = 128


def _parse_int(token: str) -> int:
    digits = token[1:] if token[:1] in "+-" else token
    if len(digits) > _MAX_INT_DIGITS:
        raise ValueError(f"整数字面量位数超过 {_MAX_INT_DIGITS} 位: {token[:32]}...")
    return int(token)


def loads(text: str) -> Any:
    """解析 JSON；整数字面量保留为任意精度 int（float 仍保留待字段校验拒绝）。"""
    return json.loads(text, parse_int=_parse_int)


def load(fp) -> Any:
    """同 ``loads``，从文件对象读取。"""
    return json.load(fp, parse_int=_parse_int)
