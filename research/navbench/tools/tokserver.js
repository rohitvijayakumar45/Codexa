// Line-delimited JSON token counter: {"t": "..."} -> {"cl100k": n, "o200k": n}
const cl = require("gpt-tokenizer/encoding/cl100k_base");
const o2 = require("gpt-tokenizer/encoding/o200k_base");
const rl = require("readline").createInterface({ input: process.stdin });
rl.on("line", (line) => {
  const { t } = JSON.parse(line);
  process.stdout.write(JSON.stringify({ cl100k: cl.encode(t, { allowedSpecial: "all" }).length, o200k: o2.encode(t, { allowedSpecial: "all" }).length }) + "\n");
});
