// 前端无损整数通道的轻量测试（Node 运行，无需 DOM）。
// 从 static/app.js 中提取纯函数 parseJsonLossless / 整数通道进行核验，
// 确保超过 Number.MAX_SAFE_INTEGER 的响应整数以 BigInt 无损保留，
// 且上送时大整数走严格十进制字符串、小整数走 number。
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(
  path.join(__dirname, "..", "static", "app.js"), "utf8");

// ---- 提取整数通道函数 ----
const c0 = src.indexOf("const INT_RE");
const c1 = src.indexOf("// ------------------------------------------------------------ 无损 JSON 解析");
const channel = src.slice(c0, c1);

// ---- 提取 parseJsonLossless（到函数完整结束）----
const p0 = src.indexOf("function parseJsonLossless");
const tailMark = "if (i < n) throw new Error";
const tailAt = src.indexOf(tailMark, p0);
const funcEnd = src.indexOf("}", src.indexOf("\n", tailAt)) + 1;
const parser = src.slice(p0, funcEnd);

const factory = new Function(
  channel + "\n" + parser +
  "\nreturn {parseExactInteger, toWireInteger, parseJsonLossless};");
const { parseExactInteger, toWireInteger, parseJsonLossless } = factory();

const BIG = "1000000000000000000000000000000"; // 10^30

// 1) 响应解析：所有整数字面量 -> BigInt，浮点仍为 number
const obj = parseJsonLossless(
  `{"total_cost":${BIG},"small":42,"neg":-7,"arr":[1,2],` +
  `"f":1.5,"s":"x","esc":"a\\"b","b":true,"n":null}`);
assert.strictEqual(obj.total_cost, BigInt(BIG));
assert.strictEqual(typeof obj.small, "bigint");
assert.strictEqual(obj.small, 42n);
assert.strictEqual(obj.neg, -7n);
assert.deepStrictEqual(obj.arr, [1n, 2n]);
assert.strictEqual(obj.f, 1.5);
assert.strictEqual(obj.s, "x");
assert.strictEqual(obj.esc, 'a"b');
assert.strictEqual(obj.b, true);
assert.strictEqual(obj.n, null);

// 2) 字符串中的数字必须保持字符串，不被误转
assert.strictEqual(parseJsonLossless(`{"a":"100"}`).a, "100");

// 3) 上送通道：小整数 number、大整数严格十进制字符串
assert.strictEqual(toWireInteger(123n), 123);
assert.strictEqual(toWireInteger(BigInt(Number.MAX_SAFE_INTEGER)),
                   Number.MAX_SAFE_INTEGER);
assert.strictEqual(toWireInteger(BigInt(Number.MAX_SAFE_INTEGER) + 1n),
                   "9007199254740992");
assert.strictEqual(toWireInteger(BigInt(BIG)), BIG);
assert.strictEqual(toWireInteger(-BigInt(BIG)), "-" + BIG);

// 4) 录入解析
assert.strictEqual(parseExactInteger(" 1000000000000000000 "),
                   1000000000000000000n);
assert.throws(() => parseExactInteger("1.5"));
assert.throws(() => parseExactInteger("1e18"));
assert.throws(() => parseExactInteger("abc"));

// 5) 非法 JSON 必须抛错（而不是静默吞掉）
assert.throws(() => parseJsonLossless(`{"a":}`));
assert.throws(() => parseJsonLossless(`[1,2,]`));
assert.throws(() => parseJsonLossless(`12 34`));

console.log("frontend lossless integer channel: ALL OK");
