/* Synthetic data and an in-browser simulator. No backend, credentials or network. */
(function(root) {
  const copy = value => JSON.parse(JSON.stringify(value));
  const now = () => Date.now() / 1000;
  const weeks = Array.from({length:16}, (_, i) => i + 1);
  const client = {refreshInterval:5,randomDeviation:.2,poolSize:1,maxLife:600,page:1,loginTimeout:30,requestTimeout:60};
  const definitions = [
    ['力学导论','物理学院',4,1,1,2,0],
    ['电磁学基础','物理学院',4,2,3,4,3],
    ['普通化学','化学与分子工程学院',4,3,1,2,0],
    ['化学实验方法','化学与分子工程学院',2,5,5,8,8],
    ['细胞生物学','生命科学学院',4,4,3,4,0],
    ['生命科学概论','生命科学学院',3,1,7,8,12],
    ['自然地理学','城市与环境学院',4,2,5,6,5],
    ['环境科学导论','城市与环境学院',3,3,7,8,0],
    ['地球科学导论','地球与空间科学学院',4,5,1,2,2],
    ['天文学入门','地球与空间科学学院',2,4,9,10,10],
    ['普通心理学','心理与认知科学学院',4,3,3,4,0],
    ['认知科学导论','心理与认知科学学院',4,1,3,4,4],
    ['数学与思维','数学科学学院',3,2,7,8,20],
    ['艺术与生活','艺术学院',2,5,9,10,0],
    ['野外实践','地球与空间科学学院',4,null,null,null,null],
  ];
  function course(row, index) {
    const [name,school,credits,day,start,end,remaining] = row;
    const raw = day ? `周${'一二三四五六日'[day-1]}第 ${start}–${end} 节，1–16 周（示例）` : '上课时间未提供（示例）';
    return {id:`demo_course_${index}`,courseCode:`DEMO${String(index+1).padStart(3,'0')}`,name:`${name}（示例）`,
      classNo:1,school,credits,teacher:`示例教师 ${index+1}`,year:index%3===0?'2026':'2025',
      types:[index<12?'专业课':'通选课'],category:index%2?'任选':'必修',pnp:'示例',major:'演示专业',
      remarks:'完全虚构的演示数据，不代表真实开课、余量或选课资格。',remaining,quota:40,
      schedule:{raw,teachingKnown:!!day,sessions:day?[{day,start,end,weeks}]:[],exam:null}};
  }
  function createDemo(saved = null) {
    const courses = definitions.map(course);
    const enrolled = [course(['高等数学','数学科学学院',5,1,1,2,0],98),course(['大学英语','外国语学院',2,4,7,8,0],99)];
    const config = {courses:[],mutexes:[],delays:{},client:copy(client)};
    const catalog = {available:courses,enrolled,note:'虚构示例课表 · 不读取任何真实账号',updatedAt:now(),
      results:[{headers:['课程名','开课单位','上课时间'],rows:enrolled.map(c=>[c.name,c.school,c.schedule.raw])}]};
    let tasks = [], serial = 0, revision = 0;
    const nextRevision=()=>`demo${String(++revision).padStart(4,'0')}`;
    function message(t, text) {
      t.events.unshift({timestamp:now(),level:'info',message:`[模拟] ${text}`});
      t.events = t.events.slice(0,100);
    }
    function validate(plan) {
      if (!plan?.courses?.length || plan.courses.length > 30) throw Error('请先选择 1–30 门示例课程');
      if (plan.courses.some(c=>!courses.some(x=>x.courseCode===c.courseCode && x.name===c.name))) throw Error('展示版仅允许内置示例课程');
      const interval = Number(plan.client?.refreshInterval);
      if (!Number.isFinite(interval) || interval<=0 || interval>3600) throw Error('演示间隔需大于 0 且不超过 3600 秒');
      return {...copy(plan),client:{...client,...plan.client,refreshInterval:interval}};
    }
    function newTask(plan) {
      const verified = validate(plan);
      if(tasks.length>=30) throw Error('演示最多保留 30 个任务，请先移除旧任务');
      const task = {id:`demo_${++serial}`,configRevision:nextRevision(),runningRevision:null,plan:verified,loops:0,lastPollAt:null,nextPollAt:null,events:[],pollLogs:[],
        state:{active:false,phase:'preparation',failure:'',courses:verified.courses.map(c=>({name:c.name,status:'待模拟',attempts:0,remaining:c.remaining}))}};
      message(task,'任务已创建，尚未启动。不会访问选课网。');
      tasks.push(task);
      return task;
    }
    if (Array.isArray(saved)) for (const item of saved.slice(0,30)) {
      try {
        const t = newTask(item.plan);
        t.loops = Number.isInteger(item.loops) && item.loops>=0 ? item.loops : 0;
        t.pollLogs = (Array.isArray(item.pollLogs)?item.pollLogs:[]).filter(e=>typeof e.message==='string' && Number.isFinite(e.timestamp)).slice(0,100);
        t.state.phase = 'stopped';
        message(t,'已从本浏览器恢复；保持停止状态，需手动启动。');
      } catch { /* Ignore invalid or obsolete demo-only storage. */ }
    }
    function tick() {
      for (const t of tasks) {
        if (!t.state.active || t.state.phase==='paused' || now()<t.nextPollAt) continue;
        t.loops++; t.lastPollAt=now();
        t.nextPollAt=now()+Math.max(.5,Number(t.plan.client.refreshInterval));
        const success=t.loops%5===0;
        const reason=success?'出现示例空位，演示成功结束（未提交真实选课）':
          ['课程暂无空位，继续等待下一轮','示例课程尚未开放，等待窗口变化','模拟网络超时，稍后重试','本轮仍无可选名额，继续等待'][(t.loops-1)%5];
        const text=`[模拟第 ${t.loops} 轮] ${t.plan.courses.map(c=>c.name).join('、')}：${reason}。`;
        t.pollLogs.unshift({timestamp:now(),message:text}); t.pollLogs=t.pollLogs.slice(0,100);
        t.state.outcome=success?null:{code:['no_seats','window_closed','network_error','no_seats'][(t.loops-1)%5],message:'模拟结果：'+reason};
        for (const c of t.state.courses) {c.status=success?'模拟成功 · 未真实选课':reason;c.remaining=success?1:0;}
        message(t,reason);
        if(success){t.state.active=false;t.state.phase='completed';t.nextPollAt=null;}
      }
    }
    function overview() {
      tick();
      return copy({config,configRevision:'synthetic-demo-v1',controlToken:'demo-only-not-a-credential',
        account:{configured:true,maskedId:'示例账号 · 无需登录',dualDegree:false,identity:'bzx'},
        control:{loggedIn:true,active:false,phase:'preparation',courses:[],captcha:{},catalog,
          export:{filename:'synthetic-demo.csv',complete:true,status:'completed',message:'内置虚构数据 · 不连接学校',rows:courses.length,pages:1}},
        runtime:{operationEnabled:false,events:[],nextPollAt:null},
        diagnostics:{pythonVersion:'展示版不运行 Python',dependencies:{},modelReady:false,modelSize:0},
        selftests:null,tasks});
    }
    function request(path, method='GET', data={}) {
      if(method==='GET' && path==='/api/overview') return overview();
      if(method==='GET' && path==='/api/course-library') return copy({courses,accountScope:'public-synthetic-demo',filename:'synthetic-demo.csv',
        complete:true,sourceRows:courses.length,missingTypes:0,modifiedAt:catalog.updatedAt});
      if(method==='POST' && path==='/api/tasks') return {task:newTask(data.plan)};
      const match=path.match(/^\/api\/tasks\/(demo_\d+)$/);
      if(method==='POST' && match) {
        const t=tasks.find(t=>t.id===match[1]); if(!t)throw Error('演示任务不存在');
        const a=data.action;
        if(['start','update'].includes(a) && data.configRevision!==t.configRevision) throw Error('演示配置已变化，请刷新后重新确认');
        if(a==='start' || a==='resume') {
          if(tasks.filter(x=>x.state.active && x!==t).length>=3) throw Error('最多同时演示 3 个任务');
          t.state.active=true;t.state.phase='running';t.runningRevision=t.configRevision;t.nextPollAt=now();message(t,'开始模拟轮询；所有操作仅在本页内执行。');
        } else if(a==='pause') {t.state.phase='paused';message(t,'模拟已暂停。');}
        else if(a==='stop') {t.state.active=false;t.state.phase='stopped';t.nextPollAt=null;message(t,'模拟已停止。');}
        else if(a==='update') {if(t.state.active)throw Error('先停止模拟再修改');t.plan=validate(data.plan);t.configRevision=nextRevision();message(t,'演示参数已更新。');}
        else if(a==='remove') {if(t.state.active)throw Error('先停止模拟再移除');tasks=tasks.filter(x=>x!==t);}
        else throw Error('展示版不支持该操作');
        return {ok:true};
      }
      if(method==='POST' && path==='/api/control' && ['read-courses','export-courses'].includes(data.action)) {
        catalog.updatedAt=now();return {ok:true,message:'仅重新载入示例数据'};
      }
      throw Error('展示版不支持登录、真实选课、退课或后端操作，请下载本地版使用。');
    }
    return {request,snapshot:()=>copy(tasks)};
  }
  if(typeof module!=='undefined') module.exports={createDemo};
  if(typeof window==='undefined') return;
  let saved=null;
  try{saved=JSON.parse(sessionStorage.getItem('pku-showcase-tasks-v1')||'null');}catch{}
  const simulator=createDemo(saved);
  // No fallback to native fetch: even unknown actions fail entirely in this browser.
  Object.defineProperty(root,'fetch',{configurable:false,writable:false,value:async function(input,options={}) {
    try {
      const url=new URL(typeof input==='string'?input:input.url,location.href);
      if(url.origin!==location.origin) throw Error('展示版禁止外部请求');
      const body=typeof options.body==='string'?JSON.parse(options.body):{};
      const result=simulator.request(url.pathname,options.method||'GET',body);
      try{sessionStorage.setItem('pku-showcase-tasks-v1',JSON.stringify(simulator.snapshot()));}catch{}
      return new Response(JSON.stringify(result),{status:200,headers:{'Content-Type':'application/json'}});
    }catch(e){return new Response(JSON.stringify({error:e.message}),{status:400,headers:{'Content-Type':'application/json'}});}
  }});
})(globalThis);
