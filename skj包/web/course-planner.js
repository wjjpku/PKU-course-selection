/* Original implementation inspired by public course-planning interaction patterns.
   Display-only: this module has no fetch, account or election operations. */
(function(root) {
  const key = c => c.courseCode ? `${c.courseCode}|${Number(c.classNo)}` : `${c.name}|${Number(c.classNo)}|${c.school}`;
  const same = (a,b) => (a.courseCode && b.courseCode ? a.courseCode===b.courseCode : a.name===b.name && a.school===b.school) && Number(a.classNo)===Number(b.classNo);
  function overlaps(a,b) {
    if(same(a,b)) return [];
    const found=new Map();
    for(const s of a.schedule?.sessions||[]) for(const t of b.schedule?.sessions||[]) {
      if(s.day!==t.day || s.start>t.end || t.start>s.end) continue;
      const weeks=[...new Set((s.weeks||[]).filter(w=>(t.weeks||[]).includes(w)))].sort((x,y)=>x-y);
      if(!weeks.length) continue;
      const slot={day:s.day,start:Math.max(s.start,t.start),end:Math.min(s.end,t.end),weeks};
      found.set(JSON.stringify(slot),slot);
    }
    return [...found.values()].sort((s,t)=>s.day-t.day || s.start-t.start || s.end-t.end);
  }
  function compare(a,b) {
    if(same(a,b)) return {teaching:false,exam:false,unknown:false};
    const x=a.schedule||{},y=b.schedule||{};
    const teaching=overlaps(a,b).length>0;
    const exam=Boolean(x.exam&&y.exam&&x.exam.date===y.exam.date&&x.exam.period===y.exam.period);
    return {teaching,exam,unknown:!x.teachingKnown||!y.teachingKnown};
  }
  function assess(course, others) {
    const conflicts=others.filter(c=>!same(c,course)).map(c=>({course:c,...compare(course,c)}));
    return {teaching:conflicts.filter(c=>c.teaching),exam:conflicts.filter(c=>c.exam),
      unknown:!course.schedule?.teachingKnown||conflicts.some(c=>c.unknown),examUnknown:!course.schedule?.exam||others.some(c=>!same(c,course)&&!c.schedule?.exam)};
  }
  function weekRanges(weeks) {
    const sorted=[...new Set(weeks)].sort((a,b)=>a-b), groups=[];
    for(let i=0;i<sorted.length;i++) {
      const first=sorted[i];let last=first;
      while(i+1<sorted.length && sorted[i+1]===last+1)last=sorted[++i];
      groups.push(first===last?String(first):`${first}–${last}`);
    }
    return groups.join('、');
  }
  function cardConflict(course,enrolled,chosen) {
    const enrolledKnown=Array.isArray(enrolled), others=[];
    for(const [courses,source] of [[enrolled||[],'已选课'],[chosen||[],'课程篮']]) {
      for(const c of courses) if(!same(c,course) && !others.some(x=>same(x.course,c))) {
        others.push({course:c,source});
      }
    }
    const checks=others.map(x=>({...x,...compare(course,x.course)}));
    const teaching=checks.filter(x=>x.teaching), exams=checks.filter(x=>x.exam);
    const unknown=checks.filter(x=>!x.course.schedule?.teachingKnown);
    const incomplete=!enrolledKnown || !course.schedule?.teachingKnown || unknown.length>0;
    const name=x=>`${x.source}《${x.course.name}》${x.course.classNo!=null?`（${x.course.classNo} 班）`:''}`;
    const lines=[];
    for(const x of teaching) {
      const times=overlaps(course,x.course).map(s=>`周${'一二三四五六日'[s.day-1]}第 ${s.start===s.end?s.start:`${s.start}–${s.end}`} 节（第 ${weekRanges(s.weeks)} 周）`);
      lines.push(`与${name(x)}冲突：${times.join('；')}。`);
    }
    for(const x of exams) {
      const exam=x.course.schedule.exam;
      lines.push(`与${name(x)}考试同在 ${exam.date.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3')} ${exam.period}，具体时间需核对。`);
    }
    if(!enrolledKnown)lines.push('尚未读取已选课表，请先读取课程后核对。');
    if(!course.schedule?.teachingKnown)lines.push('本课上课时间缺失或未完全识别，无法排除其他冲突。');
    if(unknown.length)lines.push(`${unknown.map(name).join('、')}的上课时间不完整，无法完成对照。`);
    if(!course.schedule?.exam || others.some(x=>!x.course.schedule?.exam))lines.push('部分考试时间未提供，尚不能排除考试冲突。');
    if(!teaching.length && !incomplete)lines.unshift(`与已读取的已选课及课程篮对照，上课时段未发现冲突${others.length?'':'（没有其他课程可对照）'}。`);
    return {kind:teaching.length?'conflict':incomplete||exams.length?'uncertain':'clear',
      title:teaching.length?'上课时间冲突':incomplete?'暂不能确认是否冲突':exams.length?'上课无冲突，考试时间需核对':'上课时间无冲突',lines};
  }
  const escape = value => String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
  function enrich(c,catalog) {return catalog.available.find(a=>same(a,c)) || c;}
  function selected(catalog,draft){return draft.courses.filter(c=>c.name?.trim()).map(c=>enrich(c,catalog));}
  function render(catalog,draft,preview) {
    const target=document.querySelector('#timetable-body');if(!target)return;
    const enrolled=catalog.enrolled||[];
    const chosen=selected(catalog,draft);
    const week=Number(document.querySelector('#preview-week').value);
    const all=[...enrolled.map(c=>({...c,kind:'enrolled'})),...chosen.filter(c=>!enrolled.some(e=>same(e,c))).map(c=>({...c,kind:'draft'}))];
    if(preview&&!all.some(c=>same(c,preview)))all.push({...preview,kind:'preview'});
    target.innerHTML=Array.from({length:12},(_,i)=>{
      const section=i+1;
      return `<tr><th scope="row">${section}</th>${Array.from({length:7},(_,j)=>{
        const entries=all.filter(c=>(c.schedule?.sessions||[]).some(s=>s.day===j+1&&s.start<=section&&s.end>=section&&s.weeks.includes(week)));
        return `<td>${entries.map(c=>`<span class="schedule-entry ${c.kind}" title="${escape(c.schedule?.raw)}">${escape(c.name)}</span>`).join('')}</td>`;
      }).join('')}</tr>`;
    }).join('');
    const unknown=all.filter(c=>!c.schedule?.teachingKnown);
    const issues=[];
    if(!all.length)issues.push('请先读取课程，再点击“预览课表”或加入课程篮；当前没有可检查的课程。');
    chosen.forEach((c,i)=>{
      const assessment=assess(c,[...enrolled,...chosen.slice(0,i)]);
      assessment.teaching.forEach(x=>issues.push(`${c.name} 与 ${x.course.name}：上课时间冲突`));
      assessment.exam.forEach(x=>issues.push(`${c.name} 与 ${x.course.name}：考试在同一天的同一半天，需核对具体时间`));
    });
    if(preview&&!chosen.some(c=>same(c,preview))){
      const assessment=assess(preview,[...enrolled,...chosen]);
      assessment.teaching.forEach(x=>issues.push(`预览课程 ${preview.name} 与 ${x.course.name}：上课时间冲突`));
      assessment.exam.forEach(x=>issues.push(`预览课程 ${preview.name} 与 ${x.course.name}：考试在同一天的同一半天，需核对具体时间`));
    }
    if(unknown.length)issues.push(`时间待核对：${unknown.map(c=>c.name).join('、')}。缺失信息不代表没有冲突。`);
    if(chosen.some(c=>!c.schedule?.exam)||enrolled.some(c=>!c.schedule?.exam))issues.push('部分考试时间未明确，无法完成全部考试冲突检查。');
    if(!catalog.enrolled && catalog.results?.length)issues.push('当前缓存尚无结构化课表，请重新读取课程后再核对。');
    document.querySelector('#planner-warnings').innerHTML=issues.length?issues.map(i=>`<li>${escape(i)}</li>`).join(''):'<li>已解析上课时段未发现冲突；请仍以学校原始信息为准。</li>';
    const known=chosen.filter(c=>Number.isFinite(c.credits));
    const credits=known.reduce((n,c)=>n+c.credits,0);
    document.querySelector('#basket-summary').textContent=`课程篮 ${chosen.length} 门 · 已知学分 ${credits}${known.length<chosen.length?'（部分学分缺失）':''} · 已选 ${enrolled.length} 门`;
    document.querySelector('#planner-preview').textContent=preview?`正在预览：${preview.name}（未加入不影响课程篮）`:'点击课程的“预览课表”，对照已选课程查看安排。';
  }
  const api={key,same,compare,assess,overlaps,cardConflict,enrich,selected,render};
  root.CoursePlanner=api;
  if(typeof module!=='undefined')module.exports=api;
})(globalThis);
