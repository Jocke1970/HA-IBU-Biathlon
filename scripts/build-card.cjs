#!/usr/bin/env node
// Deterministic dashboard bundle build. No external npm dependencies.
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const read = name => fs.readFileSync(path.join(root, name), "utf8");
const sv = read("frontend/translations/sv.js").replace(/^export default /, "const sv = ");
const en = read("frontend/translations/en.js").replace(/^export default /, "const en = ");
const card = read("frontend/ha-ibu-biathlon-card.js")
  .replace('import sv from "./translations/sv.js";', "")
  .replace('import en from "./translations/en.js";', "");
if (/^import /m.test(card)) throw new Error("Unexpected runtime import");
const bundle = `/* HA-IBU-Biathlon HACS dashboard bundle – generated from frontend/ */
(()=>{
"use strict";
${sv}
${en}
${card}
})();
`;
const output = path.join(root, "dist/HA-IBU-Biathlon.js");
if (process.argv.includes("--check")) {
  if (!fs.existsSync(output) || read("dist/HA-IBU-Biathlon.js") !== bundle) {
    process.stderr.write("The HACS dist bundle is outdated. Run: node scripts/build-card.cjs\\n");
    process.exit(1);
  }
  process.stdout.write("HACS dist bundle matches frontend sources\\n");
} else {
  fs.mkdirSync(path.dirname(output), {recursive:true});
  fs.writeFileSync(output, bundle);
  process.stdout.write("Built dist/HA-IBU-Biathlon.js\\n");
}
