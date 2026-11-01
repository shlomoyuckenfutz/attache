// usage: node reencrypt.js plain.html site/study/index.html  (password from env ATOUCHE_STUDY_PASSWORD or secrets file)
const fs=require('fs'),path=require('path');
const ce=require('./lib/cryptoEngine.js'),codec=require('./lib/codec.js').init(ce);
let _pw=''; try{_pw=fs.readFileSync(path.join(__dirname,'../secrets/study_password.txt'),'utf8').trim()}catch(e){} const pw=(_pw||process.env.ATOUCHE_STUDY_PASSWORD||'').trim(); if(!pw){console.error('ATOUCHE_STUDY_PASSWORD missing'); process.exit(1)}
const [plainF,siteF]=process.argv.slice(2);let site=fs.readFileSync(siteF,'utf8');
const salt=site.match(/"staticryptSaltUniqueVariableName":"([^"]*)"/)[1];
codec.encode(fs.readFileSync(plainF,'utf8'),pw,salt).then(enc=>{
 site=site.replace(/("staticryptEncryptedMsgUniqueVariableName":")[^"]*"/,(m,a)=>a+enc+'"');fs.writeFileSync(siteF,site);console.log('re-encrypted',enc.length)});
