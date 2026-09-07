/* Pure presentation: absent metadata and unrecognized errors stay unknown. */
(function(root) {
  function courseTrust(course, source={}) {
    const s=course.schedule||{}, rows=course.rawRows||[];
    const terms=[...new Set([course.term,...rows.map(r=>r['学期']||r['开课学期']||r['学年学期'])].filter(Boolean))];
    const times=[...new Set(rows.map(r=>r['查询时间']).filter(Boolean))];
    return {schedule:s.teachingKnown?'已识别':s.sessions?.length?'部分识别':s.raw?.trim()?'未识别':'缺失',
      term:terms.join(' / ')||'未提供（不能从年级推断）',
      queriedAt:times.join(' / ')||(source.updatedAt?new Date(source.updatedAt*1000).toLocaleString():'未记录'),
      timestamp:times.length?Math.min(...times.map(t=>Date.parse(t)/1000)):source.updatedAt||null};
  }
  function freshness(timestamp, now=Date.now()/1000) {
    if(!Number.isFinite(timestamp)||timestamp<=0)return '查询时间未记录或无法解析，不能判断新旧';
    if(timestamp>now+300)return '记录时间异常，请核对';
    return now-timestamp>86400?'快照超过 24 小时，建议刷新；余量不代表当前情况':'快照非实时，余量与资格以学校当前结果为准';
  }
  const reasons={
    no_seats:['等待空位','无需重复启动；按设定间隔继续检查。'],
    threshold:['尚未达到提交条件','核对任务名额阈值；达到条件后才会尝试。'],
    captcha:['验证码未通过','本轮未完成提交，下一轮重试；连续失败请检查本地识别。'],
    not_found:['当前页没有找到目标','请核对页码、班号和院系；不代表课程不存在。'],
    school_notice:['学校返回提示','尚未确认选上，请查看下方学校原始提示。'],
    ineligible:['学校提示资格不符','请到官方页面核对个人资格；重复轮询不保证能解决。'],
    pending_confirmation:['提交结果待复核','尚不能视为成功；等待读取官方已选结果。'],
    queued:['等待本轮检查','先处理前序课程或等待账号请求队列。'],
    confirmed:['官方已选结果已确认','无需再次提交该课程。'],
    mutex:['按互斥规则跳过','同组已有课程选上，因此不再尝试此课。'],
    window_closed:['当前不在操作时段','任务已停止，开放后需手动启动。'],
    school_block:['学校禁止当前自动操作','不要反复启动，请改用官方页面。'],
    session_expired:['登录会话失效','正在尝试重新登录；失败停止后需人工检查。'],
    network_error:['网络请求失败','当前余量和结果未知；运行时会退避重试，停止后请检查连接。'],
    check_failed:['本轮检查未完成','查看原始错误；不要把旧状态当作新结果。'],
  };
  function taskStatus(task, now=Date.now()/1000) {
    const s=task.state||{}, rows=s.courses||[], phase=s.phase;
    const code=s.outcome?.code||['ineligible','school_notice','not_found','captcha','pending_confirmation','threshold','no_seats','queued','confirmed','mutex'].find(c=>rows.some(r=>r.reasonCode===c));
    let [title,action]=reasons[code]||['等待新结果','查看最近日志；未识别的提示不作推断。'];
    if(!s.active){
      if(phase==='error'){title='任务已停止 · 需要处理';action='检查失败原因，处理后再手动启动。';}
      else if(phase==='waiting_window')[title,action]=reasons.window_closed;
      else if(phase==='completed'){title='任务已结束';action='核对每门课结果；互斥跳过不等于选上。';}
      else{title=phase==='preparation'?'尚未启动':'任务未运行';action='下方日志为历史记录；确认目标和参数后再启动。';}
    }else if(phase==='paused'){title='已请求暂停';action='当前请求可能仍在完成；恢复后继续检查。';}
    else if(phase==='stopping'){title='正在停止';action='等待当前请求结束，不会退掉已选课程。';}
    else if(phase==='starting'){title='正在建立登录会话';action='尚未得到本轮课程结果，请等待。';}
    const next=!s.active?'未安排下一轮':phase==='paused'?'暂停中':phase==='stopping'?'停止中':task.nextPollAt
      ? now>task.nextPollAt?'预计时间已到，可能仍在排队或等待响应':`预计 ${new Date(task.nextPollAt*1000).toLocaleTimeString()} 再检查`
      :'正在处理或等待账号请求队列';
    return {title,action,next,detail:s.failure||s.outcome?.message||'',code:code||'unknown'};
  }
  const api={courseTrust,freshness,taskStatus};root.WorkbenchInsights=api;
  if(typeof module!=='undefined')module.exports=api;
})(globalThis);
