/* global __dirname, Buffer */
// Reproducible composition: the supplied emblem pixels are embedded unchanged.
// Requires sharp from the bundled workspace runtime (no app runtime dependency).
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),sharp=require('sharp');
const root=path.resolve(__dirname,'..');
async function main(){
 const source=fs.readFileSync(path.join(__dirname,'original-logo.png'));
 const embedded='data:image/png;base64,'+source.toString('base64');
 const text=await sharp({text:{text:'Britsmaid',font:'Geist SemiBold 64',fontfile:path.join(root,'assets/fonts/Geist-SemiBold.ttf'),dpi:400,rgba:true}}).png().toBuffer();
 const word=await sharp(text).resize({width:660}).png().toBuffer();
 const wordMeta=await sharp(word).metadata();
 const wordUri='data:image/png;base64,'+word.toString('base64');
 const mark=`<svg x="230" y="112" width="564" height="580" viewBox="300 220 680 700"><image href="${embedded}" width="1280" height="1280"/></svg>`;
 const group=mark+`<image href="${wordUri}" x="182" y="736" width="660" height="${wordMeta.height}"/>`;
 const svg=scale=>`<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1024" height="1024" viewBox="0 0 1024 1024"><rect width="1024" height="1024" fill="white"/><g transform="translate(512 512) scale(${scale}) translate(-512 -512)">${group}</g></svg>`;
 // Wordmark uses the same navy as the emblem; the emblem itself is not recoloured.
 const navyWord=await sharp({create:{width:wordMeta.width,height:wordMeta.height,channels:4,background:'#0d3052'}}).composite([{input:word,blend:'dest-in'}]).png().toBuffer();
 const standard=svg(1).replace(wordUri,'data:image/png;base64,'+navyWord.toString('base64'));
 const maskable=svg(.82).replace(wordUri,'data:image/png;base64,'+navyWord.toString('base64'));
 fs.writeFileSync(path.join(__dirname,'stacked-master.svg'),standard);
 const imagePath=path.join(root,'assets/images/logo-stacked-v2.png');
 await sharp(Buffer.from(standard)).png().toFile(imagePath);
 for(const size of [64,180,192,512]) await sharp(Buffer.from(standard)).resize(size,size).png().toFile(path.join(root,`public/icons/britsmaid-${size}-v2.png`));
 await sharp(Buffer.from(maskable)).resize(512,512).png().toFile(path.join(root,'public/icons/britsmaid-maskable-512-v2.png'));
 fs.writeFileSync(path.join(__dirname,'source-integrity.json'),JSON.stringify({source:'original-logo.png',sha256:crypto.createHash('sha256').update(source).digest('hex'),emblemViewBox:[300,220,680,700],wordmark:'Britsmaid',font:'Geist-SemiBold.ttf',headerBoxUnchanged:[44,44]},null,2));
 console.log('Generated approved stacked logo and v2 icons from unchanged source emblem.');
}
main().catch(e=>{console.error(e);process.exit(1)});
