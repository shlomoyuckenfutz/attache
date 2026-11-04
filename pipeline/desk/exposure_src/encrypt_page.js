// Encrypt plain HTML into exposure lock shell using the Heat passcode (separate from Study).
// usage: node encrypt_page.js plain.html lock_shell.html out.html
// Password from ATOUCHE_HEAT_PASSWORD or ../secrets/heat_password.txt — never printed.
const fs = require('fs'), path = require('path');
const ce = require('../study_src/lib/cryptoEngine.js');
const codec = require('../study_src/lib/codec.js').init(ce);
// Heat has its own passcode (ATOUCHE_HEAT_PASSWORD / ../secrets/heat_password.txt); Study uses ATOUCHE_STUDY_PASSWORD.
let _pwFile = '';
try { _pwFile = fs.readFileSync(path.join(__dirname, '../secrets/heat_password.txt'), 'utf8').trim(); } catch (e) {}
const pw = (_pwFile || (process.env.ATOUCHE_HEAT_PASSWORD || '')).trim();
if (!pw) { console.error('ATOUCHE_HEAT_PASSWORD missing'); process.exit(1); }
const [plainF, shellF, outF] = process.argv.slice(2);
if (!plainF || !shellF || !outF) {
  console.error('usage: node encrypt_page.js plain.html lock_shell.html out.html');
  process.exit(2);
}
let shell = fs.readFileSync(shellF, 'utf8');
const saltM = shell.match(/"staticryptSaltUniqueVariableName":"([^"]*)"/);
if (!saltM) { console.error('salt missing in shell'); process.exit(1); }
const salt = saltM[1];
const plain = fs.readFileSync(plainF, 'utf8');
codec.encode(plain, pw, salt).then(enc => {
  if (!shell.includes('__ENCRYPTED__') && !/"staticryptEncryptedMsgUniqueVariableName":"[^"]*"/.test(shell)) {
    console.error('encrypted placeholder missing'); process.exit(1);
  }
  if (shell.includes('__ENCRYPTED__')) {
    shell = shell.replace('__ENCRYPTED__', enc);
  } else {
    shell = shell.replace(/("staticryptEncryptedMsgUniqueVariableName":")[^"]*"/, (_, a) => a + enc + '"');
  }
  fs.writeFileSync(outF, shell);
  console.log('encrypted ok bytes', enc.length, 'out', outF);
}).catch(e => { console.error('encrypt failed'); process.exit(1); });
