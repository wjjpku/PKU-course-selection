/* Build an explicit static allowlist. Never copy the repository or runtime data. */
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const root=path.resolve(__dirname,'..');
const destination=path.join(root,'output','vercel-showcase');
const csp="default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'";
function replace(text,from,to){if(!text.includes(from))throw Error(`Source changed; review showcase transform: ${from}`);return text.replaceAll(from,to);}
let html=fs.readFileSync(path.join(root,'skj包/web/index.html'),'utf8');
html=replace(html,'<title>燕园选课工作台</title>',`<title>燕园选课助手 · 交互展示</title><meta name="description" content="开源选课工作台交互展示：课程查询、课表冲突、课程篮与模拟任务。不接入真实账号。"><meta http-equiv="Content-Security-Policy" content="${csp}"><link rel="stylesheet" href="/assets/demo.css">`);
html=replace(html,'    <main>',`    <section class="demo-banner" aria-label="展示版说明"><div><p class="eyebrow">PKU COURSE SELECTION · INTERACTIVE DEMO</p><h2>先找课，再安心安排。</h2><p>体验课程查询、课表对照与独立任务。<strong>全部数据为虚构示例，运行仅为模拟。</strong><br>无需登录 · 不连接选课网 · 不会选课或退课 · 暂未接入数据库</p></div><div class="panel-actions"><a class="button primary" href="https://github.com/wjjpku/PKU-course-selection/releases/tag/v0.1.0" target="_blank" rel="noopener noreferrer">下载本地版</a><button class="button secondary" id="demo-reset">重置演示</button></div></section>\n    <main>`);
html=replace(html,'    <script src="/assets/course-query.js" defer></script>','    <script src="/assets/demo.js" defer></script>\n    <script src="/assets/course-query.js" defer></script>');
html=replace(html,'    <script src="/assets/app.js" defer></script>','    <script src="/assets/app.js" defer></script>\n    <script src="/assets/demo-ui.js" defer></script>');
html=replace(html,'<input id="account-password"','<input disabled id="account-password"');
html=replace(html,'<input id="account-id"','<input disabled id="account-id"');
let app=fs.readFileSync(path.join(root,'skj包/web/app.js'),'utf8');
for(const [a,b] of [
  ['pku-elective-preparation-draft-v1','pku-showcase-preparation-draft-v1'],
  ['本地服务已连接','交互展示 · 无学校连接'],
  ['创建刷课任务','创建模拟任务'],
  ['课程字段已从学校读取','课程字段已从示例读取'],
  ['课程库快照 ·','虚构示例快照 ·'],
  ['独立刷课任务','独立任务 · 浏览器内模拟'],
]) app=replace(app,a,b);
const files={'index.html':html,'assets/app.js':app};
for(const name of ['styles.css','planner.css','course-query.js','course-planner.js','workbench-insights.js'])files['assets/'+name]=fs.readFileSync(path.join(root,'skj包/web',name),'utf8');
for(const name of ['demo.js','demo-ui.js','demo.css'])files['assets/'+name]=fs.readFileSync(path.join(root,'showcase',name),'utf8');
files['vercel.json']=JSON.stringify({version:2,framework:null,buildCommand:null,installCommand:null,outputDirectory:'.',
  headers:[{source:'/(.*)',headers:[{key:'Content-Security-Policy',value:csp+"; frame-ancestors 'none'"},
    {key:'X-Content-Type-Options',value:'nosniff'},{key:'Referrer-Policy',value:'no-referrer'},
    {key:'X-Frame-Options',value:'DENY'},{key:'Permissions-Policy',value:'camera=(), microphone=(), geolocation=()'}]}]},null,2)+'\n';
// Fail closed if anything unexpected is present; never deploy a dirty output folder.
function entries(dir){return fs.existsSync(dir)?fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?entries(path.join(dir,e.name)):[path.relative(destination,path.join(dir,e.name))]):[];}
for(const file of entries(destination))if(!Object.hasOwn(files,file) && !file.startsWith('.vercel/') && file!=='.gitignore')throw Error('Unexpected deploy file: '+file);
for(const [name,content] of Object.entries(files)) {
  if(/(?:gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----)/.test(content))throw Error('Secret-like content in '+name);
  const target=path.join(destination,name);fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,content);
}
console.log(JSON.stringify({directory:destination,files:Object.keys(files),bytes:Object.values(files).reduce((n,s)=>n+Buffer.byteLength(s),0),sha256:crypto.createHash('sha256').update(Object.values(files).join('')).digest('hex')},null,2));
