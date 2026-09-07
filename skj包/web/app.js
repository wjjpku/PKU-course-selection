const STORAGE_KEY = "pku-elective-preparation-draft-v1";
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = { server: null, draft: null, activeView: "plan", saving: false, connected: false };
state.directory = 'select';
state.preview = null;
state.library = {courses:[],loaded:false,loading:false,error:'',filename:null};
state.query = CourseQuery.defaults();
state.queryScope = null;
state.queryMatches = [];

function saveQuery() {
  if(!state.queryScope)return;
  try {localStorage.setItem('pku-course-query-v1:'+state.queryScope,JSON.stringify(state.query));}
  catch {$('#query-feedback').textContent='浏览器不允许保存筛选条件，本次查询仍可使用。';}
}

async function loadCourseLibrary(force=false) {
  if(!state.server || state.library.loading)return;
  const key=JSON.stringify([state.server.account,state.server.control.export?.filename]);
  if(!force && state.library.loadKey===key)return;
  const accountHint=JSON.stringify(state.server.account);
  if(state.library.accountHint && state.library.accountHint!==accountHint)state.library={courses:[],loaded:false,filename:null};
  state.library.accountHint=accountHint;
  state.library.loading=true;state.library.loadKey=key;state.library.error='';
  try {
    const response=await fetch('/api/course-library',{cache:'no-store'});
    if(!response.ok) {
      const data=await response.json().catch(()=>({}));
      throw Error(data.error || (response.status===404?'后端尚未提供课程库查询，请加载新版后端。':'课程库暂不可用，请重试。'));
    }
    const data=await response.json();
    if(!Array.isArray(data.courses))throw Error('课程库返回格式不正确');
    state.library={...data,loaded:true,loading:false,error:'',loadKey:key,accountHint};
    if(state.queryScope!==data.accountScope) {
      state.queryScope=data.accountScope;
      try {state.query=CourseQuery.clean(JSON.parse(localStorage.getItem('pku-course-query-v1:'+state.queryScope)||'null'));}
      catch {state.query=CourseQuery.defaults();}
    }
  } catch(error) {
    state.library.loading=false;state.library.error=error.message;
  }
  renderCatalog(state.server.control.catalog);
}

function browseCatalog(catalog) {
  return {...catalog,available:state.query.source==='library'?state.library.courses:catalog.available};
}

function syncQueryControls(courses) {
  const f=state.query, facets=CourseQuery.facets(courses);
  const options=(values,chosen,label)=>`<option value="">${label}</option>`+[...new Set([...values,...(chosen?[chosen]:[])])].map(v=>`<option value="${escapeAttr(v)}" ${v===chosen?'selected':''}>${escapeHtml(v)}${values.includes(v)?'':'（当前数据无此项）'}</option>`).join('');
  $('#query-type').innerHTML=options(facets.types,f.type,'所有入口');
  $('#query-credits').innerHTML=options(facets.credits,f.credits,'不限');
  for(const [group,label] of [['departments','院系'],['years','面向年级']]) {
    const values=[...new Set([...facets[group],...f[group]])];
    $('#query-'+group).innerHTML=values.map(v=>`<label><input type="checkbox" data-query-group="${group}" value="${escapeAttr(v)}" ${f[group].includes(v)?'checked':''}>${escapeHtml(v)}</label>`).join('')||'<p>当前数据未提供选项</p>';
    $('#query-'+group+'-summary').textContent=label+' · '+(f[group].length?f[group].join('、'):'不限');
  }
  $('#course-search').value=f.q;
  $('#query-source').value=f.source;
  $('#catalog-filter').value=f.availability;
  $('#catalog-sort').value=f.sort;
}

function showDirectory(directory) {
  state.directory = directory;
  const loggedIn = Boolean(state.server?.control.loggedIn);
  $('#main-menu').hidden = false;
  $('#select-workspace').hidden = directory !== 'select';
  $('#run-workspace').hidden = directory !== 'run';
  $('#debug-workspace').hidden = directory !== 'debug';
  $('#account-panel').hidden = loggedIn || directory !== 'select';
  $('#account-exit').hidden = !loggedIn;
  $('#account-panel').open = !loggedIn;
  $$('.next-action-bar').forEach(el => el.hidden = directory !== 'select');
  $$('[data-directory]').forEach(button => {
    button.classList.toggle('primary', button.dataset.directory === directory);
    button.classList.toggle('secondary', button.dataset.directory !== directory);
    button.setAttribute('aria-current', button.dataset.directory === directory ? 'page' : 'false');
  });
}

function renderJourney() {
  if (!state.server || !state.draft) return;
  const c = state.server.control;
  const count = state.draft.courses.filter(c => c.name?.trim()).length;
  const errors = validateDraft().filter(i => i.level === 'error');
  let action, title, hint, label;
  if (!state.connected) [action,title,hint,label] = ['retry','与本地服务断开连接','保留你的草稿；恢复连接前不能保存或启动。','重新连接'];
  else if (c.active) [action,title,hint,label] = ['status','任务进行中','查看每门课的最新状态；暂停或停止不影响已经选上的课。','查看运行'];
  else if (!c.loggedIn) [action,title,hint,label] = ['account','先登录账号','登录后即可选择课程并进入刷课栏。','登录账号'];
  else if (!count) [action,title,hint,label] = ['catalog','还没有选定目标','从学校课程中点选，字段会自动填好。','选择课程'];
  else if (errors.length) [action,title,hint,label] = ['review',`已选 ${count} 门 · 有 ${errors.length} 项待处理`,errors[0].message,'检查问题'];
  else [action,title,hint,label] = ['save',`待创建：${count} 门课程`,'创建独立任务后再启动；每个任务单独循环，共用账号限速。','创建刷课任务'];
  $('#journey-title').textContent = title;
  $('#journey-hint').textContent = hint;
  $('#journey-next').textContent = state.saving ? '正在保存…' : label;
  $('#journey-next').dataset.action = action;
  $('#journey-next').disabled = state.saving;
}

function planKey(plan) {
  return JSON.stringify([plan.courses.map(c => [c.id, c.name, Number(c.classNo), c.school]),
    plan.mutexes.map(m => m.courses), Object.entries(plan.delays).sort(),
    ['refreshInterval','randomDeviation','poolSize','maxLife','page','loginTimeout','requestTimeout'].map(k => Number(plan.client[k]))]);
}

function draftIsDirty() { return planKey(state.draft) !== planKey(state.server.config); }

function prepareSelectedPlan(plan) {
  // An unnamed legacy entry cannot identify a target. Keep real named choices.
  plan.courses = plan.courses.filter(c => c.name?.trim());
  const ids = new Set(plan.courses.map(c => c.id));
  plan.mutexes = plan.mutexes.map(m => ({...m, courses:[...new Set(m.courses.filter(id => ids.has(id)))]}))
    .filter(m => m.courses.length >= 2);
  for (const id of Object.keys(plan.delays)) if (!ids.has(id)) delete plan.delays[id];
  const deviation = Number(plan.client.randomDeviation);
  if (!Number.isFinite(deviation) || deviation < 0 || deviation >= 1) plan.client.randomDeviation = .2;
  const interval = Number(plan.client.refreshInterval);
  if (!Number.isFinite(interval) || interval <= 0) plan.client.refreshInterval = 5;
}

function fillMissingCourseFields(catalog) {
  let count = 0;
  for (const course of state.draft.courses) {
    if (!course.name?.trim()) continue; // Never guess which course the user wants.
    if (course.school?.trim() && course.classNo !== '' && course.classNo != null) continue;
    const matches = catalog.available.filter(c => c.name === course.name &&
      (!course.school?.trim() || c.school === course.school) &&
      (course.classNo === '' || course.classNo == null || Number(course.classNo) === Number(c.classNo)));
    if (matches.length !== 1) continue;
    Object.assign(course, {school:matches[0].school, classNo:matches[0].classNo});
    count++;
  }
  if (count) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.draft));
    $('#save-feedback').textContent = `已从学校数据补齐 ${count} 门课的字段，尚未应用。`;
    renderCourses();
  }
}

function escapeHtml(value) {
  const node = document.createElement("span");
  node.textContent = String(value ?? "");
  return node.innerHTML;
}

function escapeAttr(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function cloneConfig(config) {
  return JSON.parse(JSON.stringify({
    courses: config.courses,
    mutexes: config.mutexes,
    delays: config.delays,
    client: config.client,
  }));
}

function loadDraft(config) {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (saved?.courses && saved?.client) return saved;
  } catch (_) {
    localStorage.removeItem(STORAGE_KEY);
  }
  return cloneConfig(config);
}

function saveDraft(message = "草稿已自动保存") {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.draft));
  $("#draft-status").textContent = message;
  showToast(message);
  renderAll();
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("is-visible");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("is-visible"), 2200);
}

function minimumInterval(client = state.draft.client) {
  return Math.max(0, Number(client.refreshInterval) * (1 - Math.max(0, Number(client.randomDeviation))));
}

function validateDraft() {
  const issues = [];
  const identities = new Set();

  state.draft.courses.forEach((course, index) => {
    const label = course.name?.trim() || course.id || `第 ${index + 1} 门课程`;
    if (!course.id?.trim()) issues.push({ level: "error", message: `${label}缺少课程标识` });
    if (!course.name?.trim()) issues.push({ level: "error", message: `课程 ${course.id || index + 1} 缺少课程名称` });
    if (!course.school?.trim()) issues.push({ level: "error", message: `${label}缺少开课单位` });
    if (!Number.isInteger(Number(course.classNo)) || Number(course.classNo) < 0) {
      issues.push({ level: "error", message: `${label}的班号必须是非负整数` });
    }
    const identity = `${course.name?.trim()}|${Number(course.classNo)}|${course.school?.trim()}`;
    if (identities.has(identity)) issues.push({ level: "error", message: `${label}与另一门目标课程重复` });
    identities.add(identity);
  });

  state.draft.mutexes.forEach((mutex) => {
    const existing = mutex.courses.filter((id) => state.draft.courses.some((course) => course.id === id));
    if (new Set(existing).size < 2 || existing.length !== mutex.courses.length) issues.push({ level: "error", message: `互斥组 ${mutex.id} 需至少两门有效课程，请修正或删除该组` });
  });

  const min = minimumInterval();
  for (const key of ['refreshInterval','randomDeviation','poolSize','maxLife','page','loginTimeout','requestTimeout']) {
    if (!Number.isFinite(Number(state.draft.client[key]))) issues.push({level:'error', message:`请求参数 ${key} 必须是有限数字`});
  }
  const client = state.draft.client;
  if (!(client.randomDeviation >= 0 && client.randomDeviation < 1)) issues.push({level:'error', message:'随机偏移必须在 0 到 1 之间（不含 1）'});
  if (!Number.isInteger(Number(client.page)) || client.page < 1) issues.push({level:'error', message:'课程页码必须是正整数'});
  if (!(client.loginTimeout > 0 && client.requestTimeout > 0)) issues.push({level:'error', message:'登录与请求超时必须为正数'});
  if (!(Number(client.maxLife) === -1 || client.maxLife > 0)) issues.push({level:'error', message:'会话寿命必须为 -1 或正数'});
  if (min <= 0) issues.push({ level: "error", message: '轮询间隔必须大于 0' });
  if (Number(state.draft.client.poolSize) < 1 || Number(state.draft.client.poolSize) > 5) {
    issues.push({ level: "error", message: "会话池大小必须介于 1—5" });
  }
  if (!state.draft.courses.length) issues.push({ level: "error", message: "还没有添加目标课程" });
  return issues;
}

function renderMetrics() {
  const errors = validateDraft().filter((issue) => issue.level === "error");
  $("#course-count").textContent = String(state.draft.courses.length);
  $("#issue-count").textContent = errors.length ? `${errors.length} 项` : "通过";
  $("#min-interval").textContent = `${minimumInterval().toFixed(1)}s`;
}

function renderCourses() {
  const list = $("#course-list");
  if (!state.draft.courses.length) {
    list.className = "empty-state";
    list.innerHTML = '<div><strong>尚未添加目标课程</strong><span>先添加一门课程，再设置优先级和互斥规则。</span></div>';
    return;
  }

  list.className = "course-list";
  list.innerHTML = state.draft.courses.map((course, index) => {
    const threshold = state.draft.delays[course.id];
    return `
      <div class="course-row ${course.name?.trim() ? "" : "has-error"}" data-index="${index}">
        <span class="priority">${String(index + 1).padStart(2, "0")}</span>
        <div>
          <div class="course-name">${escapeHtml(course.name || "未填写课程名")}</div>
          <div class="course-meta">${escapeHtml(course.school || "未填写开课单位")} · ${escapeHtml(course.id)}</div>
        </div>
        <span class="course-value">班号 ${Number(course.classNo)}</span>
        <span class="course-value">${threshold ? `剩余 ≤ ${threshold}` : "有空位即尝试"}</span>
        <div class="row-actions" aria-label="${escapeAttr(course.name || course.id)} 操作">
          <button class="icon-button" data-action="up" title="提高优先级" ${index === 0 ? "disabled" : ""}>↑</button>
          <button class="icon-button" data-action="down" title="降低优先级" ${index === state.draft.courses.length - 1 ? "disabled" : ""}>↓</button>
          <button class="text-button" data-action="edit">编辑</button>
          <button class="text-button danger" data-action="delete" title="只移出本地课程篮，不会退课">移出课程篮</button>
        </div>
      </div>`;
  }).join("");
}

function renderRules() {
  $('#course-page').value = state.draft.client.page ?? 1;
  $('#login-timeout').value = state.draft.client.loginTimeout ?? 30;
  $('#request-timeout').value = state.draft.client.requestTimeout ?? 60;
  $("#refresh-interval").value = state.draft.client.refreshInterval;
  $("#random-deviation").value = state.draft.client.randomDeviation;
  $("#pool-size-input").value = state.draft.client.poolSize;
  $("#max-life").value = state.draft.client.maxLife;

  const min = minimumInterval();
  const result = $("#policy-result");
  result.className = `policy-result ${min <= 0 ? "is-error" : "is-safe"}`;
  result.innerHTML = `<span>计算后最低间隔</span><strong>${min.toFixed(2)} 秒</strong><small>按你的设置轮询；请求串行，网络错误时退避等待。</small>`;

  const list = $("#mutex-list");
  if (!state.draft.mutexes.length) {
    list.innerHTML = '<div class="empty-state small">当前没有互斥规则</div>';
    return;
  }
  const names = Object.fromEntries(state.draft.courses.map((course) => [course.id, course.name || course.id]));
  list.innerHTML = state.draft.mutexes.map((mutex, index) => `
    <div class="rule-row">
      <div><strong>互斥组 ${escapeHtml(mutex.id)}</strong><div class="chip-list">${mutex.courses.map((id) => `<span>${escapeHtml(names[id] || id)}</span>`).join("")}</div></div>
      <button class="text-button danger" data-mutex-index="${index}">删除</button>
    </div>`).join("");
}

function renderDiagnostics() {
  const issues = validateDraft();
  const checks = [
    ...issues,
    { level: "success", message: "未明确授权时，程序不会登录或访问选课网" },
    { level: "success", message: "学号、密码和会话信息不会发送给前端" },
    { level: "success", message: "工作台仅监听本机回环地址" },
  ];
  const blocking = checks.filter((item) => item.level === "error").length;
  const score = Math.max(0, 100 - blocking * 25 - checks.filter((item) => item.level === "warning").length * 8);
  $("#readiness-score").textContent = `${score}%`;
  $("#issue-list").innerHTML = checks.map((item) => `<div class="check-item ${item.level}">${escapeHtml(item.message)}</div>`).join("");

  const diagnostics = state.server.diagnostics;
  const dependencies = Object.entries(diagnostics.dependencies);
  $("#diagnostic-list").innerHTML = `
    <div><dt>Python</dt><dd>${escapeHtml(diagnostics.pythonVersion)}</dd></div>
    ${dependencies.map(([name, ready]) => `<div><dt>${escapeHtml(name)}</dt><dd class="${ready ? "ready" : "missing"}">${ready ? "已就绪" : "未安装"}</dd></div>`).join("")}
    <div><dt>ONNX 模型</dt><dd class="${diagnostics.modelReady ? "ready" : "missing"}">${diagnostics.modelReady ? `${(diagnostics.modelSize / 1024 / 1024).toFixed(1)} MB` : "缺失"}</dd></div>
    <div><dt>网络暴露</dt><dd class="ready">仅本机</dd></div>`;

  const events = state.server.runtime.events;
  $("#event-list").innerHTML = events.length
    ? events.map((event) => `<div class="event-row"><time>${new Date(event.timestamp * 1000).toLocaleTimeString("zh-CN")}</time><span>${escapeHtml(event.message)}</span></div>`).join("")
    : '<div class="empty-state small">准备期尚未产生运行事件</div>';
}

function renderAll() {
  if (!state.draft || !state.server) return;
  renderMetrics();
  renderCourses();
  renderRules();
  renderDiagnostics();
  renderControl();
}

function setView(view) {
  showDirectory(view === 'diagnostics' ? 'debug' : 'select');
  if(view==='rules')$('#task-settings').open=true;
  state.activeView = view;
  $$(".tab").forEach((button) => {
    const active = button.dataset.view === view;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
  $$(".app-view").forEach((panel) => {
    const active = panel.id === `view-${view}`;
    panel.hidden = false;
    panel.classList.add("is-active");
  });
  $(`#view-${view}`)?.scrollIntoView({behavior:'smooth',block:'start'});
}

function openCourseDialog(index = null) {
  const editing = index !== null;
  const course = editing ? state.draft.courses[index] : { id: "", name: "", classNo: 1, school: "" };
  $("#course-dialog-title").textContent = editing ? "编辑课程" : "添加课程";
  $("#editing-index").value = editing ? String(index) : "";
  $("#course-id").value = course.id;
  $("#course-name").value = course.name;
  $("#course-class").value = course.classNo;
  $("#course-school").value = course.school;
  $("#course-threshold").value = state.draft.delays[course.id] ?? "";
  $("#course-form-error").textContent = "";
  $("#course-dialog").showModal();
  $("#course-name").focus();
}

function saveCourse() {
  const indexValue = $("#editing-index").value;
  const index = indexValue === "" ? null : Number(indexValue);
  const oldId = index === null ? null : state.draft.courses[index].id;
  const course = {
    id: $("#course-id").value.trim(),
    name: $("#course-name").value.trim(),
    classNo: Number($("#course-class").value),
    school: $("#course-school").value.trim(),
    priority: index === null ? state.draft.courses.length + 1 : index + 1,
  };
  const error = $("#course-form-error");
  if (!course.id || !course.name || !course.school || !Number.isInteger(course.classNo) || course.classNo < 0) {
    error.textContent = "请完整填写课程标识、名称、班号和开课单位。";
    return;
  }
  if (!/^[A-Za-z0-9_-]+$/.test(course.id)) {
    error.textContent = "课程标识只能包含字母、数字、下划线和连字符。";
    return;
  }
  if (state.draft.courses.some((item, itemIndex) => item.id === course.id && itemIndex !== index)) {
    error.textContent = "课程标识不能重复。";
    return;
  }

  if (index === null) state.draft.courses.push(course);
  else state.draft.courses[index] = course;

  if (oldId && oldId !== course.id) {
    if (state.draft.delays[oldId]) {
      state.draft.delays[course.id] = state.draft.delays[oldId];
      delete state.draft.delays[oldId];
    }
    state.draft.mutexes.forEach((mutex) => {
      mutex.courses = mutex.courses.map((id) => id === oldId ? course.id : id);
    });
  }
  const threshold = Number($("#course-threshold").value);
  if (threshold > 0) state.draft.delays[course.id] = threshold;
  else delete state.draft.delays[course.id];

  $("#course-dialog").close();
  saveDraft(index === null ? "课程已添加" : "课程已更新");
}

function openMutexDialog() {
  $("#mutex-form-error").textContent = "";
  $("#mutex-options").innerHTML = state.draft.courses.map((course) => `
    <label><input type="checkbox" value="${escapeAttr(course.id)}" /><span><strong>${escapeHtml(course.name || course.id)}</strong><small>${escapeHtml(course.school)}</small></span></label>`).join("");
  $("#mutex-dialog").showModal();
}

function saveMutex() {
  const selected = $$("#mutex-options input:checked").map((input) => input.value);
  if (selected.length < 2) {
    $("#mutex-form-error").textContent = "请至少选择两门课程。";
    return;
  }
  const existingIds = state.draft.mutexes.map((mutex) => Number(mutex.id)).filter(Number.isFinite);
  const id = String(existingIds.length ? Math.max(...existingIds) + 1 : 0);
  state.draft.mutexes.push({ id, courses: selected });
  $("#mutex-dialog").close();
  saveDraft("互斥组已添加");
}

function exportPlan() {
  if (validateDraft().some((issue) => issue.level === "error")) {
    setView("diagnostics");
    showToast("请先修复阻断性配置问题");
    return;
  }
  const client = state.draft.client;
  const lines = [
    "; 由燕园选课工作台导出。不包含学号或密码。",
    "[client]",
    "supply_cancel_page = 1",
    `refresh_interval = ${client.refreshInterval}`,
    `random_deviation = ${client.randomDeviation}`,
    "iaaa_client_timeout = 30",
    "elective_client_timeout = 60",
    `elective_client_pool_size = ${client.poolSize}`,
    `elective_client_max_life = ${client.maxLife}`,
    "login_loop_interval = 2",
    "print_mutex_rules = true",
    "debug_print_request = false",
    "debug_dump_request = false",
    "", "[monitor]", "host = 127.0.0.1", "port = 7074", "",
  ];
  state.draft.courses.forEach((course) => {
    lines.push(`[course:${course.id}]`, `name = ${course.name}`, `class = ${course.classNo}`, `school = ${course.school}`, "");
  });
  state.draft.mutexes.forEach((mutex) => {
    lines.push(`[mutex:${mutex.id}]`, `courses = ${mutex.courses.join(",")}`, "");
  });
  Object.entries(state.draft.delays).forEach(([course, threshold], index) => {
    lines.push(`[delay:${index}]`, `course = ${course}`, `threshold = ${threshold}`, "");
  });
  const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "course-plan.safe.ini";
  link.click();
  URL.revokeObjectURL(link.href);
  showToast("安全配置已导出");
}

function bindEvents() {
  $('#catalog-panel h2').textContent='课程查询';
  $('#catalog-panel .eyebrow').textContent='先找课，再安排';
  $('#catalog-panel [data-command="read-courses"]').textContent='刷新已选课表';
  const exportPanel=document.createElement('details');exportPanel.className='query-sync';exportPanel.id='course-export-panel';
  exportPanel.innerHTML='<summary>更新课程库 / 下载原始 CSV</summary><p class="course-meta">更新会只读查询学校当前账号可见的分类与分页，不包含大纲详情；每次请求至少间隔 4 秒（仅全量导出）。本地搜索无需登录或反复请求学校，加入课程篮不会立即选课。</p><div class="panel-actions"><button type="button" class="button secondary" id="export-courses-start">更新课程库</button><button type="button" class="button ghost" id="export-courses-stop" hidden>停止查询并保留部分结果</button><a class="button secondary" id="export-courses-download" href="/api/course-export/download" hidden>下载 CSV</a></div><p id="export-courses-status" role="status" aria-live="polite">尚未查询</p>';
  $('#catalog-note').after(exportPanel);
  $('#export-courses-start').addEventListener('click',async()=>{const b=$('#export-courses-start');b.disabled=true;try{await post('/api/control',{action:'export-courses'});await refreshStatus();}catch(e){reportError(e);}finally{renderControl();}});
  $('#export-courses-stop').addEventListener('click',async()=>{try{await post('/api/control',{action:'stop'});await refreshStatus();}catch(e){reportError(e);}});
  const planner=document.createElement('div');planner.className='planner-layout';
  const browse=document.createElement('div');browse.className='course-browser';
  const tools=$('.catalog-tools');const note=tools.nextElementSibling;
  browse.append(tools,note,$('#available-courses'));
  const calendar=document.createElement('aside');calendar.className='timetable-panel';
  calendar.innerHTML='<div class="panel-heading"><h3>我的课表 · 对照预览</h3><label>教学周 <select id="preview-week" aria-label="预览教学周"></select></label></div><p class="course-meta">手动选择教学周，非自动当前周；冲突提示会检查所有已解析教学周。</p><p class="schedule-legend"><span class="enrolled">已选</span><span class="draft">课程篮</span><span class="preview">正在预览</span></p><p id="basket-summary"></p><p id="planner-preview" class="course-meta"></p><div class="timetable-scroll"><table class="timetable"><thead><tr><th>节</th><th>一</th><th>二</th><th>三</th><th>四</th><th>五</th><th>六</th><th>日</th></tr></thead><tbody id="timetable-body"></tbody></table></div><ul id="planner-warnings" aria-live="polite"></ul>';
  const filters=document.createElement('div');filters.className='catalog-filters';
  filters.innerHTML='<label>查询范围<select id="query-source"><option value="library">本地全量课程库</option><option value="current">已读取选课页</option></select></label><label>课程类型（查询入口）<select id="query-type"></select></label><label>学分<select id="query-credits"></select></label><details class="query-multi"><summary id="query-departments-summary">院系 · 不限</summary><div id="query-departments"></div></details><details class="query-multi"><summary id="query-years-summary">面向年级 · 不限</summary><div id="query-years"></div></details><label>显示 <select id="catalog-filter"><option value="all">全部课程</option><option value="seats">有余量（快照）</option><option value="basket">已加入课程篮</option></select></label><label>排序 <select id="catalog-sort"><option value="school">学校原顺序</option><option value="seats">余量从多到少</option><option value="name">课程名称</option><option value="credits">学分从多到少</option></select></label><button type="button" class="button ghost" id="query-reset">清空筛选</button>';
  browse.insertBefore(filters,browse.querySelector('#available-courses'));
  const actions=document.createElement('div');actions.className='query-actions';
  actions.innerHTML='<button type="button" class="button ghost" id="query-science">快捷：理科院系 · 4 学分 · 2025/2026 级</button><button type="button" class="button ghost" id="query-reload">重新载入本地数据</button><button type="button" class="button secondary" id="query-export">导出筛选结果</button><button type="button" class="button ghost" id="toggle-timetable" aria-expanded="false" aria-controls="course-calendar">展开课表</button><a class="button secondary" id="basket-link" href="#view-plan">查看课程篮</a><p id="query-feedback" role="status" aria-live="polite"></p>';
  filters.after(actions);
  const pagination=document.createElement('nav');pagination.className='query-pagination';pagination.setAttribute('aria-label','课程查询分页');
  pagination.innerHTML='<button type="button" class="button ghost" id="query-prev">上一页</button><span id="query-page" role="status"></span><button type="button" class="button ghost" id="query-next">下一页</button>';
  browse.append(pagination);
  const basketStrip=document.createElement('p');basketStrip.id='basket-strip';basketStrip.className='basket-strip';browse.insertBefore(basketStrip,browse.querySelector('#available-courses'));
  calendar.id='course-calendar';calendar.hidden=true;planner.classList.add('list-only');
  const toggleCalendar=(open)=>{calendar.hidden=!open;planner.classList.toggle('list-only',!open);$('#toggle-timetable').textContent=open?'收起课表':'展开课表';$('#toggle-timetable').setAttribute('aria-expanded',String(open));};
  planner.append(browse,calendar);$('#catalog-panel').append(planner);
  $('#toggle-timetable').addEventListener('click',()=>toggleCalendar(calendar.hidden));
  const updateQuery=()=>{state.query.page=1;$('#query-feedback').textContent='';saveQuery();if(state.server)renderCatalog(state.server.control.catalog);};
  for(const [id,field] of [['#catalog-filter','availability'],['#catalog-sort','sort'],['#query-type','type'],['#query-credits','credits'],['#query-source','source']])$(id).addEventListener('change',()=>{state.query[field]=$(id).value;updateQuery();});
  filters.addEventListener('change',event=>{const input=event.target.closest('[data-query-group]');if(!input)return;const group=input.dataset.queryGroup;state.query[group]=[...filters.querySelectorAll(`[data-query-group="${group}"]:checked`)].map(x=>x.value);updateQuery();});
  $('#query-reset').addEventListener('click',()=>{state.query={...CourseQuery.defaults(),source:state.query.source};updateQuery();});
  $('#query-science').addEventListener('click',()=>{state.query={...CourseQuery.defaults(),source:state.query.source,credits:'4',years:['2025','2026'],departments:['物理学院','化学与分子工程学院','生命科学学院','城市与环境学院','地球与空间科学学院','心理与认知科学学院']};updateQuery();});
  $('#query-reload').addEventListener('click',()=>loadCourseLibrary(true));
  for(const [id,step] of [['#query-prev',-1],['#query-next',1]])$(id).addEventListener('click',()=>{state.query.page+=step;saveQuery();renderCatalog(state.server.control.catalog);$('.catalog-tools').scrollIntoView({block:'start'});});
  $('#query-export').addEventListener('click',()=>{
    if(!state.queryMatches.length)return;
    const courses=state.queryMatches.map(x=>x.course), url=URL.createObjectURL(new Blob([CourseQuery.csv(courses)],{type:'text/csv;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download='courses-filtered-'+new Date().toISOString().slice(0,10)+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    $('#query-feedback').textContent=`已导出全部 ${courses.length} 条筛选结果（不只本页）；多个查询入口的原始行分别保留。`;
  });
  $('.catalog-tools label').textContent='搜索课程库';
  note.textContent='本地组合筛选，空格分隔多个关键词。课程类型按查询入口；年级不是个人选课资格保证。冲突直接显示在卡片上，缺失时间不会当成无冲突。';
  $('#course-search').placeholder='课程名、课程号、教师、院系、专业或备注';
  const clearPreview=document.createElement('button');clearPreview.className='button ghost';clearPreview.textContent='清除预览';clearPreview.type='button';calendar.append(clearPreview);
  clearPreview.addEventListener('click',()=>{state.preview=null;CoursePlanner.render(browseCatalog(state.server.control.catalog),state.draft,null);});
  $('#preview-week').innerHTML=Array.from({length:32},(_,i)=>`<option value="${i+1}">第 ${i+1} 周</option>`).join('');
  $('#preview-week').addEventListener('change',()=>CoursePlanner.render(browseCatalog(state.server.control.catalog),state.draft,state.preview));
  let theme='auto';try{theme=localStorage.getItem('workbench-theme')||'auto';}catch{}
  if(!['auto','light','dark'].includes(theme))theme='auto';
  const systemTheme=matchMedia('(prefers-color-scheme: dark)');
  const applyTheme=()=>{document.documentElement.dataset.theme=theme==='auto'?(systemTheme.matches?'dark':'light'):theme;$('#theme-toggle').textContent={auto:'主题：跟随系统',light:'主题：浅色',dark:'主题：深色'}[theme];$('#theme-toggle').title='点击切换：跟随系统 → 浅色 → 深色';};applyTheme();
  systemTheme.addEventListener('change',applyTheme);
  $('#theme-toggle').addEventListener('click',()=>{theme={auto:'light',light:'dark',dark:'auto'}[theme];try{localStorage.setItem('workbench-theme',theme);}catch{}applyTheme();});
  $('#available-courses').addEventListener('click',event=>{
    const preview=event.target.closest('[data-preview-course]');if(!preview)return;
    state.preview=browseCatalog(state.server.control.catalog).available[Number(preview.dataset.previewCourse)];
    toggleCalendar(true);
    CoursePlanner.render(browseCatalog(state.server.control.catalog),state.draft,state.preview);
    if(innerWidth<1000)calendar.scrollIntoView({behavior:'smooth',block:'start'});
  });
  document.addEventListener('click',async event=>{
    const test=event.target.closest('[data-test]');
    if(test){test.disabled=true;try{await post('/api/selftest',{test:test.dataset.test});await refreshStatus();}catch(e){reportError(e);}finally{test.disabled=false;}return;}
    const button=event.target.closest('[data-task-action]');if(!button)return;
    const task=state.server.tasks.find(t=>t.id===button.dataset.taskId);if(!task)return;
    const action=button.dataset.taskAction;
    if(action==='start'){
      $('#start-targets').innerHTML=task.plan.courses.map(c=>`<li>${escapeHtml(c.name)} · 班号 ${escapeHtml(c.classNo)}</li>`).join('');
      $('#start-policy').textContent=`仅启动此任务。基础等待 ${task.plan.client.refreshInterval} 秒；请求串行，无固定 4 秒下限。`;
      $('#start-dialog').dataset.taskId=task.id;$('#start-dialog').showModal();return;
    }
    let plan;
    if(action==='update'){
      const interval=prompt('此任务的基础等待秒数（停止后才能修改，必须大于 0）',task.plan.client.refreshInterval);
      if(interval===null)return;
      plan=JSON.parse(JSON.stringify(task.plan));plan.client.refreshInterval=Number(interval);
    }
    if(action==='remove'&&!confirm('只移除此本地任务，不会从学校退课。继续？'))return;
    button.disabled=true;
    try{await post(`/api/tasks/${task.id}`,{action,plan});await refreshStatus();}catch(e){reportError(e);}finally{button.disabled=false;}
  });
  const debugButton=document.createElement('button');debugButton.className='button secondary';debugButton.dataset.directory='debug';debugButton.textContent='系统调试';$('#main-menu').insertBefore(debugButton,$('#account-exit'));
  const run = $('#run-workspace');
  $('#select-workspace').append($('#catalog-panel'));
  for (const node of [$('.stage-banner'),$('.metrics'),$('#view-plan'),$('#view-rules'),$('#live-courses').closest('section'),$('#view-diagnostics')]) run.append(node);
  $('#select-workspace').prepend($('#account-panel'));
  $('#select-workspace').append($('#view-plan'));
  $('#view-plan').append($('.next-action-bar'));
  $('#view-plan h2').textContent='课程篮 · 确认后创建任务';
  const settings=document.createElement('details');settings.className='panel';settings.id='task-settings';settings.innerHTML='<summary>新任务参数与课程规则</summary>';
  settings.append($('#view-rules'));$('#select-workspace').append(settings);
  $('#debug-workspace').append($('#view-diagnostics'));
  const legacy=document.createElement('div');legacy.hidden=true;
  legacy.append($('.stage-banner'),$('.metrics'),$('#live-courses').closest('section'));run.append(legacy);
  const jobs=document.createElement('section');jobs.className='panel';jobs.innerHTML='<h2>独立刷课任务</h2><p>最多同时运行 3 个任务，请求串行；轮询按各任务设置。新版后端使用本地数据库保存任务和最近日志，重启后恢复为停止状态，需手动启动。</p><div id="task-list"></div>';run.prepend(jobs);
  $$('.app-view').forEach(node=>{node.hidden=false;node.classList.add('is-active');});
  $('.workflow').hidden=true;
  $('.view-tabs').hidden=true;
  $$('[data-directory]').forEach(button=>button.addEventListener('click',()=>{showDirectory(button.dataset.directory);renderJourney();}));
  $('#account-exit').addEventListener('click',()=> $('[data-command="logout"]').click());
  $('#login-enter').addEventListener('click',async()=>{
    const button=$('#login-enter');button.disabled=true;
    try {
      if ($('#account-id').value || $('#account-password').value || !state.server.account.configured ||
          ($('#account-dual').value==='true') !== state.server.account.dualDegree || $('#account-identity').value !== state.server.account.identity) {
        await post('/api/config',{account:{studentId:$('#account-id').value,password:$('#account-password').value,dualDegree:$('#account-dual').value==='true',identity:$('#account-identity').value}});
        $('#account-password').value='';$('#account-id').value='';
      }
      state.directory='select';
      await post('/api/control',{action:'read-courses'});
      await refreshStatus();
    } catch(error){reportError(error);} finally{button.disabled=false;}
  });
  $('#journey-next').addEventListener('click', async () => {
    const action = $('#journey-next').dataset.action;
    if (action === 'run') { showDirectory('run'); renderJourney(); window.scrollTo({top:0,behavior:'smooth'}); return; }
    if (action === 'retry') { try { if (state.server) await refreshStatus(); else await loadOverview(); } catch (error) { reportError(error); } return; }
    if (action === 'account') { $('#account-panel').open = true; $('#account-id').focus(); return; }
    if (action === 'catalog') { $('#pick-course').click(); return; }
    if (action === 'status') { showDirectory('run'); $('#live-courses').scrollIntoView({behavior:'smooth',block:'center'}); return; }
    if (action === 'review') {
      setView('plan');
      $('#save-feedback').textContent = validateDraft().filter(i => i.level === 'error').map(i => i.message).join('；');
      $('#save-feedback').scrollIntoView({behavior:'smooth',block:'center'}); return;
    }
    if (action === 'save') { $('#persist-plan').click(); return; }
    if (action === 'start') $('[data-command="start"]').click();
  });
  $('#confirm-start').addEventListener('click', async () => {
    const button = $('#confirm-start');
    button.disabled = true;
    try {
      if ($('#start-dialog').dataset.taskId) {
        await post(`/api/tasks/${$('#start-dialog').dataset.taskId}`,{action:'start'});
        $('#start-dialog').close();await refreshStatus();return;
      }
      if (!state.connected || draftIsDirty()) throw new Error('状态或草稿已变化，请重新核对后启动');
      await post('/api/control', {action:'start', configRevision:$('#start-dialog').dataset.revision});
      $('#start-dialog').close();
      await refreshStatus();
      $('#live-courses').scrollIntoView({behavior:'smooth',block:'center'});
    } catch (error) { $('#start-dialog').close(); reportError(error); }
    finally { button.disabled = false; }
  });
  $('#course-search').addEventListener('input', () => {state.query.q=$('#course-search').value;state.query.page=1;$('#query-feedback').textContent='';saveQuery();if(state.server)renderCatalog(state.server.control.catalog);});
  $('.workflow a[href="#view-plan"]').addEventListener('click', () => setView('plan'));
  $('#export-events').addEventListener('click', () => {
    const content = state.server.runtime.events.map(e => `${new Date(e.timestamp*1000).toLocaleString()} [${e.level}] ${e.message}`).join('\n');
    const url = URL.createObjectURL(new Blob([content], {type:'text/plain;charset=utf-8'}));
    const link = document.createElement('a'); link.href=url; link.download='运行记录.txt'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  $('#account-form').addEventListener('submit', e => e.preventDefault());
  $('#client-form').addEventListener('submit', e => e.preventDefault());
  $('#persist-plan').addEventListener('click', async () => {
    if (state.saving) return;
    const errors = validateDraft().filter(i => i.level === 'error');
    if (errors.length) {
      $('#save-feedback').textContent = '未保存：' + errors.map(i => i.message).join('；');
      reportError(new Error('配置未保存，请查看目标课程上方的具体原因'));
      return;
    }
    state.saving = true;
    const submittedKey = planKey(state.draft);
    renderControl();
    try {
      await post('/api/tasks', {plan: cloneConfig(state.draft)});
      await refreshStatus();
      if (planKey(state.draft) === submittedKey) {
        state.draft.courses=[];state.draft.mutexes=[];state.draft.delays={};
        localStorage.setItem(STORAGE_KEY,JSON.stringify(state.draft));
      }
      renderAll();
      $('#draft-status').textContent = '已创建任务，未启动';
      showToast('已创建独立任务，尚未启动');
      $('#save-feedback').textContent = '任务已创建；可以继续选课创建其他任务。';
      showDirectory('run');
    } catch (error) {
      $('#save-feedback').textContent = '任务创建失败：' + error.message;
      reportError(error);
    } finally { state.saving = false; renderControl(); }
  });
  $('#persist-account').addEventListener('click', async () => {
    try {
      await post('/api/config', {account: {studentId: $('#account-id').value,
        password: $('#account-password').value, dualDegree: $('#account-dual').value === 'true',
        identity: $('#account-identity').value}});
      $('#account-password').value = '';
      $('#account-id').value = '';
      await refreshStatus();
      showToast('账号已保存');
    } catch (error) { reportError(error); }
  });
  $$('[data-command]').forEach(button => button.addEventListener('click', async () => {
    if (state.saving) return;
    if (button.dataset.command === 'start' && draftIsDirty()) {
      reportError(new Error('草稿尚未应用，已阻止启动旧配置。请先保存并应用。'));
      return;
    }
    if (button.dataset.command === 'start') {
      const errors = validateDraft().filter(i => i.level === 'error');
      if (errors.length) { reportError(new Error(errors.map(i => i.message).join('；'))); return; }
      $('#start-targets').innerHTML = state.server.config.courses.map(c => `<li>${escapeHtml(c.name)} · 班号 ${escapeHtml(c.classNo)} · ${escapeHtml(c.school)}</li>`).join('');
      $('#start-policy').textContent = `基础等待 ${state.server.config.client.refreshInterval} 秒；只处理这些目标课程。`;
      $('#start-dialog').dataset.revision = state.server.configRevision;
      $('#start-dialog').showModal();
      return;
    }
    button.disabled = true;
    try {
      await post('/api/control', {action: button.dataset.command, configRevision: state.server.configRevision});
      await refreshStatus();
    } catch(error) { reportError(error); }
    finally { renderControl(); }
  }));
  $$(".tab").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
  $("#add-course").addEventListener("click", () => openCourseDialog());
  $('#pick-course').addEventListener('click', async () => {
    showDirectory('select'); renderJourney();
    $('#available-courses').scrollIntoView({behavior:'smooth', block:'center'});
    if (!state.server.control.catalog?.updatedAt && !state.server.control.active) {
      try {
        await post('/api/control', {action:'read-courses'});
        await refreshStatus();
      } catch (error) { reportError(error); }
    }
  });
  $("#save-course").addEventListener("click", saveCourse);
  $("#add-mutex").addEventListener("click", openMutexDialog);
  $("#save-mutex").addEventListener("click", saveMutex);
  $("#export-plan").addEventListener("click", exportPlan);
  $("#reset-draft").addEventListener("click", () => {
    localStorage.removeItem(STORAGE_KEY);
    state.draft = cloneConfig(state.server.config);
    $("#draft-status").textContent = "已恢复当前配置";
    showToast("已恢复当前配置");
    renderAll();
  });

  $("#course-list").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const index = Number(button.closest("[data-index]").dataset.index);
    const action = button.dataset.action;
    if (action === "edit") return openCourseDialog(index);
    if (action === "delete") {
      const [removed] = state.draft.courses.splice(index, 1);
      delete state.draft.delays[removed.id];
      state.draft.mutexes = state.draft.mutexes
        .map((mutex) => ({ ...mutex, courses: mutex.courses.filter((id) => id !== removed.id) }))
        .filter((mutex) => mutex.courses.length);
      return saveDraft("课程已从草稿移除");
    }
    const next = action === "up" ? index - 1 : index + 1;
    if (next >= 0 && next < state.draft.courses.length) {
      [state.draft.courses[index], state.draft.courses[next]] = [state.draft.courses[next], state.draft.courses[index]];
      saveDraft("课程优先级已更新");
    }
  });

  $("#mutex-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-mutex-index]");
    if (!button) return;
    state.draft.mutexes.splice(Number(button.dataset.mutexIndex), 1);
    saveDraft("互斥组已删除");
  });

  $("#client-form").addEventListener("input", (event) => {
    const key = event.target.name;
    if (!key) return;
    state.draft.client[key] = Number(event.target.value);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.draft));
    $("#draft-status").textContent = "请求策略仅存为草稿，尚未应用";
    renderMetrics();
    const result = $('#policy-result');
    result.className = `policy-result ${minimumInterval() <= 0 ? 'is-error' : 'is-safe'}`;
    result.textContent = `最低间隔：${minimumInterval().toFixed(2)} 秒`;
    renderDiagnostics();
    renderControl();
  });
}

async function loadOverview() {
  const response = await fetch("/api/overview", { cache: "no-store" });
  if (!response.ok) throw new Error("服务响应异常");
  state.server = await response.json();
  state.connected = true;
  state.draft = loadDraft(state.server.config);
  $('#account-dual').value = String(state.server.account.dualDegree);
  $('#account-identity').value = state.server.account.identity;
  $('#account-panel').open = !state.server.account.configured;
  renderAll();
  renderControl();
}

function reportError(error) {
  $('#control-error').textContent = error.message;
  showToast(error.message);
}

async function post(url, data) {
  $('#control-error').textContent = '';
  const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json',
    'X-Control-Token': state.server.controlToken}, body:JSON.stringify(data)});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || '操作失败，请刷新后重试');
  return payload;
}

function renderControl() {
  if (!state.server?.control) return;
  const c = state.server.control;
  const exportState=c.export;
  const tasksBusy=(state.server.tasks||[]).some(t=>t.state.active);
  $('#export-courses-start').disabled=!state.connected||!exportState||c.active||tasksBusy;
  $('#export-courses-stop').hidden=!(c.active&&exportState?.status==='running');
  $('#export-courses-download').hidden=!exportState?.filename||exportState.status==='running';
  $('#export-courses-download').textContent=exportState?.complete?'下载完整 CSV':'下载部分 CSV（未完成）';
  $('#export-courses-status').textContent=!exportState?'需加载新版后端后使用':`${exportState.message} · 已读取 ${exportState.pages||0} 页 / ${exportState.rows||0} 条${exportState.groupsTotal?` · 分类进度 ${exportState.groupsDone||0}/${exportState.groupsTotal}`:''}${tasksBusy?'；请先停止刷课任务，再开始全量查询':''}`;
  showDirectory(state.directory);
  $('#run-target-count').textContent = (state.server.tasks || []).length;
  $('#login-enter').disabled = !state.connected || c.active;
  $('#login-enter').textContent = c.active ? '正在登录并读取…' : '登录并读取课程';
  const names = {preparation:'准备就绪', starting:'正在登录', running:'正在运行', paused:'已请求暂停',
    stopping:'正在停止', stopped:'已停止', completed:'任务完成', error:'运行出错',
    testing:'正在测试验证码', reading:'正在只读查询课程', ready:'检查完成', waiting_window:'当前不在操作时段'};
  $('#stage-title').textContent = names[c.phase] || c.phase;
  $('#control-hint').textContent = c.active ? '任务运行中，使用已保存配置' : draftIsDirty() ? '存在未应用草稿，请先保存；不会启动旧配置' : '启动将使用已生效配置';
  $('#effective-plan').textContent = '此栏是下一项任务的课程篮。创建后课程和参数独立保存，不会覆盖其他任务。';
  $('#account-status').textContent = `${state.server.account.maskedId || '未配置账号'} · ${c.loggedIn ? '已登录' : '未登录'}`;
  $('#live-timing').textContent = state.server.runtime.nextPollAt
    ? `下次检查：${new Date(state.server.runtime.nextPollAt*1000).toLocaleTimeString()}` : '等待任务';
  $('#live-courses').innerHTML = c.courses.length ? c.courses.map(row =>
    `<div class="event-row"><strong>${escapeHtml(row.name)}</strong><span>${escapeHtml(row.status)} · 余量 ${row.remaining ?? '—'} · 提交 ${row.attempts} 次</span></div>`).join('') : '尚未运行课程检查';
  $('#live-captcha').textContent = c.captcha.code
    ? `验证码：${c.captcha.code} · ${c.captcha.latencyMs} ms · ${c.captcha.validation || ''} ${c.captcha.total ? `· ${c.captcha.correct}/${c.captcha.total} 正确` : ''}` : '尚无验证码识别记录';
  if (c.failure) $('#control-error').textContent = c.failure;
  $$('[data-command]').forEach(button => {
    const action = button.dataset.command;
    button.hidden = ['pause','stop'].includes(action) ? !c.active : action === 'resume' ? c.phase !== 'paused' : action === 'start' ? c.active : false;
    button.disabled = !state.connected || state.saving || (['start','login','ocr-test','read-courses'].includes(action) ? c.active
      : action === 'pause' ? !c.active || ['paused','stopping'].includes(c.phase)
      : action === 'resume' ? c.phase !== 'paused'
      : action === 'stop' ? !c.active : false);
  });
  $('[data-command="login"]').hidden=true;
  $('[data-command="logout"]').hidden=true;
  $('#persist-plan').disabled = !state.connected || c.active || state.saving;
  $('#persist-plan').textContent = state.saving ? '正在创建…' : '创建刷课任务';
  $('#save-badge').textContent = '待创建课程篮 · 不会自动运行';
  $('#persist-account').disabled = !state.connected || c.active || state.saving;
  renderCatalog(c.catalog);
  loadCourseLibrary();
  renderJourney();
  renderTaskModules();
}

function renderTaskModules(){
  const tasks=state.server.tasks||[];
  const open=new Set($$('#task-list details[open]').map(el=>el.dataset.logs));
  const signature=JSON.stringify(tasks);
  if(renderTaskModules.signature!==signature){
    renderTaskModules.signature=signature;
    $('#task-list').innerHTML=tasks.length?tasks.map(t=>{
      const s=t.state;
      const names={preparation:'待启动',starting:'登录中',running:'运行中',paused:'已请求暂停',stopping:'停止中',stopped:'已停止',completed:'全部完成',error:'运行失败',waiting_window:'不在操作时段'};
      const actions=s.active?(s.phase==='paused'?['resume','stop']:['pause','stop']):['start','update','remove'];
      const labels={start:'启动此任务',pause:'暂停',resume:'继续',stop:'停止',update:'调整间隔',remove:'移除任务'};
      return `<article class="task-card"><div class="panel-heading"><h3>${escapeHtml(t.plan.courses.map(c=>c.name).join('、'))}</h3><span class="badge">${escapeHtml(names[s.phase]||s.phase)}</span></div><p>任务 ${escapeHtml(t.id)} · ${t.loops} 轮 · 基础等待 ${escapeHtml(t.plan.client.refreshInterval)} 秒</p><div class="panel-actions">${actions.map(a=>`<button class="button secondary" data-task-id="${t.id}" data-task-action="${a}">${labels[a]}</button>`).join('')}</div>${s.failure?`<p class="form-error">${escapeHtml(s.failure)}</p>`:''}<ul>${s.courses.map(c=>`<li>${escapeHtml(c.name)}：${escapeHtml(c.status)} · 提交 ${c.attempts} 次 · 余量 ${c.remaining??'—'}</li>`).join('')}</ul><details data-logs="${t.id}" ${open.has(t.id)?'open':''}><summary>任务日志（${t.events.length}）</summary><pre>${escapeHtml(t.events.map(e=>`${new Date(e.timestamp*1000).toLocaleTimeString()} ${e.message}`).join('\n')||'尚无日志')}</pre></details></article>`;
    }).join(''):'还没有任务。回到选课首页，选入课程篮，再点击“创建刷课任务”。';
    $$('#task-list > .task-card').forEach((card,index)=>{
      const task=tasks[index];
      const history=document.createElement('section');history.className='poll-history';
      const heading=document.createElement('h4');heading.textContent=`刷课日志 · 最近 ${(task.pollLogs||[]).length} / 100 条`;
      const hint=document.createElement('p');hint.className='course-meta';hint.textContent='最新在上；每次轮询结果单独保留，超过 100 条自动淘汰最旧记录。';
      const log=document.createElement('pre');
      log.textContent=task.pollLogs===undefined?'当前服务尚未加载新版轮询日志，需要重启后端后生效。':task.pollLogs.map(e=>`${new Date(e.timestamp*1000).toLocaleTimeString()} ${e.message}`).join('\n\n')||'尚无轮询结果，开始检查后会自动记录。';
      history.append(heading,hint,log);card.insertBefore(history,card.querySelector('details'));
      const timing=document.createElement('p');timing.className='course-meta';
      const last=task.lastPollAt?new Date(task.lastPollAt*1000).toLocaleTimeString():'尚未完成检查';
      const next=task.state.phase==='paused'?'已暂停，恢复后继续':!task.state.active?'任务未运行':task.nextPollAt?`预计 ${new Date(task.nextPollAt*1000).toLocaleTimeString()} 再检查（排队可能延后）`:'正在检查或等待账号请求队列';
      timing.textContent=`最近检查：${last} · ${next}`;
      card.insertBefore(timing,card.querySelector('details'));
      const latest=document.createElement('p');latest.className='course-meta';
      latest.textContent=`最新动态：${task.events[0]?.message||'等待任务启动'}`;
      card.insertBefore(latest,card.querySelector('details'));
    });
  }
  const tests=state.server.selftests;
  if(tests){
    const key=JSON.stringify(tests);
    if(renderTaskModules.testKey!==key){renderTaskModules.testKey=key;
      $('#selftest-list').innerHTML=tests.results.map(t=>`<div class="task-card"><h3>${escapeHtml(t.name)}</h3><p>${escapeHtml(t.status)} ${t.durationMs==null?'':`· ${t.durationMs} ms`}</p><button class="button secondary" data-test="${t.id}" ${tests.running?'disabled':''}>运行测试</button><details><summary>查看测试详情</summary><pre>${escapeHtml(t.detail||'尚无结果')}</pre></details></div>`).join('');
    }
    $('[data-test="all"]').disabled=tests.running;
  }
}

function renderCatalog(catalog) {
  if (!catalog) return;
  const originalCatalog=catalog;
  catalog=browseCatalog(catalog);
  fillMissingCourseFields(catalog);
  const signature = JSON.stringify([originalCatalog, state.draft.courses, state.query, state.library.filename,
    state.library.modifiedAt,state.library.loading,state.library.error]);
  if (renderCatalog.signature === signature) return;
  renderCatalog.signature = signature;
  syncQueryControls(catalog.available);
  $('#enrolled-count').textContent = `（${catalog.results.reduce((n,t) => n+t.rows.length, 0)} 门）`;
  const chosen=CoursePlanner.selected(catalog,state.draft);
  const matches=CourseQuery.filter(catalog.available,state.query,chosen,CoursePlanner.same);
  state.queryMatches=matches;
  const totalPages=Math.max(1,Math.ceil(matches.length/24));
  state.query.page=Math.max(1,Math.min(state.query.page,totalPages));
  const visible=matches.slice((state.query.page-1)*24,state.query.page*24);
  $('#query-prev').disabled=state.query.page<=1;
  $('#query-next').disabled=state.query.page>=totalPages;
  $('#query-page').textContent=`第 ${state.query.page} / ${totalPages} 页 · 每页 24 条`;
  $('#query-export').disabled=!matches.length;
  $('#query-reload').disabled=state.library.loading;
  $('#basket-link').textContent=`查看课程篮（${chosen.length}）`;
  $('#basket-strip').textContent=chosen.length?`课程篮：${chosen.map(c=>c.name).join('、')}。仅在本地，创建任务后还需单独启动。`:'先找到课程 → 加入课程篮 → 确认参数并创建任务。加入不会立即选课。';
  if(state.preview)state.preview=catalog.available.find(c=>CoursePlanner.same(c,state.preview))||null;
  CoursePlanner.render(catalog,state.draft,state.preview);
  $('#catalog-count').textContent = `找到 ${matches.length} / ${catalog.available.length} 条课程记录`;
  const lib=state.library;
  $('#catalog-note').textContent=state.query.source==='library'
    ? lib.error || (lib.loading?'正在载入本地课程库…':lib.filename?`课程库快照 · ${lib.complete?'已完成分类查询':'部分结果，尚不完整'} · ${lib.sourceRows} 条原始记录 · ${new Date(lib.modifiedAt*1000).toLocaleString()}${lib.missingTypes?` · ${lib.missingTypes} 条缺少查询入口，重新更新课程库后才能按类型筛选`:''}。余量非实时；查询不会访问学校。`:'尚未建立本地课程库。展开“更新课程库”，登录后同步一次，之后即可在本地查询。')
    : `${catalog.note} ${catalog.updatedAt ? '· 最近读取 ' + new Date(catalog.updatedAt * 1000).toLocaleString() : ''}`;
  if(state.query.source==='library' && catalog.updatedAt)$('#catalog-note').textContent+=` 已选课表对照：${new Date(catalog.updatedAt*1000).toLocaleString()}${catalog.note?.includes('历史缓存')?'（历史缓存，建议刷新）':''}。`;
  $('#enrolled-courses').innerHTML = catalog.results.length ? catalog.results.map(table =>
    `<div class="catalog-table"><table><thead><tr>${table.headers.map(h => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead><tbody>${table.rows.map(row => `<tr>${row.map(cell => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`).join('') : '尚无成功读取的选课结果';
  const detailScope=state.query.source+':'+(state.library.filename||'');
  const openDetails=new Set(renderCatalog.detailScope===detailScope?$$('[data-course-detail][open]').map(e=>e.dataset.courseDetail):[]);
  renderCatalog.detailScope=detailScope;
  $('#available-courses').innerHTML = visible.length ? visible.map(({course, index}) => {
    const exists = state.draft.courses.some(c => c.name === course.name && Number(c.classNo) === Number(course.classNo) && c.school === course.school);
    const check=CoursePlanner.cardConflict(course,catalog.enrolled,chosen);
    const conflictNote=`<div class="course-conflict-note ${check.kind}"><p class="course-conflict-title">${escapeHtml(check.title)}</p><ul>${check.lines.map(line=>`<li>${escapeHtml(line)}</li>`).join('')}</ul></div>`;
    const canAdd=course.name&&course.school&&course.classNo!=null;
    const rawFields=course.rawRows?.[0]||{'课程类别':course.category||'未提供','上课与考试':course.schedule?.raw||'时间未提供'};
    return `<article class="event-row catalog-card ${exists ? 'is-selected' : ''}"><div><p class="course-type">${escapeHtml(CourseQuery.types(course).join(' / '))}</p><strong>${escapeHtml(course.name)}</strong><p>${escapeHtml(course.courseCode||'课程号未提供')} · ${escapeHtml(course.school||'院系未提供')} · 班号 ${escapeHtml(course.classNo??'未提供')}</p><p>${escapeHtml(course.teacher||'教师未提供')} · ${course.credits??'—'} 学分 · 面向 ${escapeHtml(course.year||'年级未提供')}</p><p class="course-time">${escapeHtml(course.schedule?.raw||'上课时间未提供')}</p><span class="quota ${course.remaining > 0 ? 'has-seats' : ''}">${course.remaining==null?'余量未知':course.remaining > 0 ? `快照余量 ${escapeHtml(course.remaining)} / ${escapeHtml(course.quota)}` : '已满 · 可加入等待'}</span><span class="course-meta"> · P/NP：${escapeHtml(course.pnp||'未提供')}</span>${conflictNote}<details data-course-detail="${index}"><summary>查看全部原始信息</summary><dl class="course-fields">${Object.entries(rawFields).map(([k,v])=>`<div><dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v||'未提供')}</dd></div>`).join('')}</dl></details></div><div class="panel-actions"><button class="button ghost" data-preview-course="${index}" aria-label="${escapeAttr('预览课表：'+course.name)}">预览课表</button><button class="button secondary" data-add-catalog="${index}" ${canAdd?'':'disabled title="课程字段不完整，不能创建任务"'} aria-pressed="${exists}" aria-label="${escapeAttr((exists ? '移出本地计划：' : '加入计划：') + course.name + '，班号 ' + course.classNo)}">${exists ? '✓ 已加入 · 移出' : '+ 加入课程篮'}</button></div></article>`;
  }).join('') : catalog.available.length?'没有符合全部条件的课程。试试减少条件或点击“清空筛选”；不会自动隐藏缺少时间的课程。':'当前范围暂无课程。可以更新课程库，或切换到“已读取选课页”。';
  $$('[data-course-detail]').forEach(el=>{el.open=openDetails.has(el.dataset.courseDetail);});
  $$('[data-add-catalog]').forEach(button => button.addEventListener('click', () => {
    const course = catalog.available[Number(button.dataset.addCatalog)];
    const existing = state.draft.courses.findIndex(c => c.name === course.name && Number(c.classNo) === Number(course.classNo) && c.school === course.school);
    if (existing >= 0) {
      state.draft.courses.splice(existing, 1);
      prepareSelectedPlan(state.draft);
      saveDraft('已移出本地草稿，不是学校退课');
      return;
    }
    let id = 'course_' + Date.now();
    while (state.draft.courses.some(c => c.id === id)) id += '_1';
    state.draft.courses.push({...course, id});
    prepareSelectedPlan(state.draft);
    $('#save-feedback').textContent = '课程字段已从学校读取；保留你的轮询间隔。仅修改课程篮，尚未启动。';
    saveDraft('已自动填好课程信息，无需手填；尚未启动选课');
  }));
}

async function refreshStatus() {
  try {
  const response = await fetch('/api/overview', {cache:'no-store'});
  if (!response.ok) throw new Error('状态读取失败');
  state.server = await response.json();
  state.connected = true;
  $('#connection').textContent = '本地服务已连接';
  renderControl();
  renderDiagnostics();
  } catch (error) {
    state.connected = false;
    $('#connection').textContent = '连接中断 · 草稿已保留';
    renderControl();
    throw error;
  }
}

setInterval(() => {
  if (state.server) refreshStatus().catch(() => {});
}, 2000);

bindEvents();
loadOverview().catch((error) => {
  $("#connection").innerHTML = '<span class="status-dot error"></span>本地服务连接失败';
  $("#course-list").className = "empty-state";
  $("#course-list").textContent = error.message;
  $('#journey-title').textContent = '暂时无法连接本地工作台';
  $('#journey-hint').textContent = '请确认本地服务已启动。你的草稿不会被清空。';
  $('#journey-next').textContent = '重新连接';
  $('#journey-next').dataset.action = 'retry';
  $('#journey-next').disabled = false;
});
