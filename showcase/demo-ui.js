/* Presentation-only overrides. The local workbench source stays unchanged. */
const originalDemoControl = renderControl;
renderControl = function() {
  originalDemoControl();
  $('#connection').textContent='交互展示 · 无学校连接';
  $('#export-courses-start').textContent='重新载入示例数据';
  $('#export-courses-download').hidden=true;
  $('#export-courses-status').textContent='15 门完全虚构的示例课程；查询、导出和任务模拟均在浏览器内完成。';
  $('#persist-plan').textContent=state.saving?'正在创建…':'创建模拟任务';
  $('#account-panel').hidden=true;
  $('#account-exit').hidden=true;
  $('[data-command="read-courses"]').textContent='重新载入示例课表';
  $$('.task-card [data-task-action="start"]').forEach(b=>b.textContent='启动模拟');
};
renderDiagnostics = function() {
  $('#readiness-score').textContent='展示版';
  $('#issue-list').innerHTML='<div class="check-item success">不接入真实账号，也不调用学校接口</div><div class="check-item success">仅发布静态网页和虚构示例数据</div><div class="check-item success">浏览器网络策略禁止后台连接与表单提交</div>';
  $('#diagnostic-list').innerHTML='<div><dt>运行方式</dt><dd>浏览器内模拟</dd></div><div><dt>数据来源</dt><dd>15 门虚构课程 + 2 门虚构已选课</dd></div><div><dt>数据库</dt><dd>尚未接入</dd></div><div><dt>任务保存</dt><dd>当前浏览器标签页；刷新后恢复为停止</dd></div>';
  $('#event-list').textContent='这里不会显示任何真实账号日志。任务页显示的轮询与结果均为模拟。';
};
$('#account-form').querySelectorAll('input,select').forEach(el=>el.disabled=true);
$('#debug-workspace > article').innerHTML='<div class="panel-heading"><h2>展示版说明</h2></div><p>在线版不运行 Python、OCR 或真实后端测试。完整版本及离线测试请从 GitHub 下载。</p>';
$('#run-workspace > .panel > p').textContent='这是浏览器内模拟：每 5 轮演示一次成功，不提交选课。间隔、暂停、停止和最近 100 条日志均可体验；关闭页面不会继续运行。';
$('#course-export-panel > p').textContent='课程、时间、教师和余量全部为虚构示例。可用“导出筛选结果”下载示例 CSV。';
$('#start-dialog .dialog-form > p').textContent='仅模拟下面课程的轮询过程，不登录学校、不提交选课。';
$('#confirm-start').textContent='确认并启动模拟';
$('#query-source option[value="library"]').textContent='内置示例课程库';
$('#query-source option[value="current"]').textContent='示例选课页';
$('#add-course').hidden=true;
$('#demo-reset').addEventListener('click',()=>{
  if(!confirm('重置当前浏览器内的演示课程篮、筛选与模拟任务？不影响本地刷课服务。'))return;
  sessionStorage.removeItem('pku-showcase-tasks-v1');
  localStorage.removeItem('pku-showcase-preparation-draft-v1');
  localStorage.removeItem('pku-course-query-v1:public-synthetic-demo');
  location.reload();
});
if(state.server){renderControl();renderDiagnostics();}
