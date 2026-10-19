const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const pub = path.join(root, "public");
const web = path.join(root, "web");
const assets = path.join(root, "assets");

function cpDir(src, dest) {
  if (!fs.existsSync(src)) return;
  fs.mkdirSync(dest, { recursive: true });
  for (const name of fs.readdirSync(src)) {
    const s = path.join(src, name);
    const d = path.join(dest, name);
    if (fs.statSync(s).isDirectory()) cpDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

fs.rmSync(pub, { recursive: true, force: true });
fs.mkdirSync(pub, { recursive: true });
for (const f of fs.readdirSync(web)) {
  const s = path.join(web, f);
  if (fs.statSync(s).isFile()) fs.copyFileSync(s, path.join(pub, f));
}
cpDir(assets, path.join(pub, "assets"));
console.log("Built public/ for Vercel");
