// Encrypt plain HTML into exposure lock shell using SAME password+salt as Study Room.
// usage: node encrypt_page.js plain.html lock_shell.html out.html
// Password from ATOUCHE_STUDY_PASSWORD or ../secrets/study_password.txt — never printed.
const fs = require('fs'), path = require('path');
const ce = require('../study_src/lib/cryptoEngine.js');
const codec = require('../study_src/lib/codec.js').init(ce);
let _pwFile = '';
try { _pwFile = fs.readFileSync(path.join(__dirname, '../secrets/study_password.txt'), 'utf8').trim(); } catch (e) {}
const pw = (_pwFile || (process.env.ATOUCHE_STUDY_PASSWORD || '')).trim();
if (!pw) { console.error('ATOUCHE_STUDY_PASSWORD missing'); process.exit(1); }
if (_pwFile && process.env.ATOUCHE_STUDY_PASSWORD && process.env.ATOUCHE_STUDY_PASSWORD.trim() !== _pwFile) {
  console.warn('encrypt_page: ignoring ATOUCHE_STUDY_PASSWORD (differs from secrets file)');
}
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
