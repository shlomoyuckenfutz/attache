// Encrypt Project B plain HTML with SAME password+salt as Study/Heat.
const {spawnSync}=require('child_process');
const path=require('path');
const [plain, shell, out] = process.argv.slice(2);
const r = spawnSync('node', [
  path.join(__dirname, '../exposure_src/encrypt_page.js'),
  plain, shell, out
], {stdio:'inherit'});
process.exit(r.status||0);
