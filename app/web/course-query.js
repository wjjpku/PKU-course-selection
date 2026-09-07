/* Independent local query helpers. No network, credentials or course actions. */
(function(root) {
  const defaults=()=>({q:'',type:'',departments:[],years:[],credits:'',availability:'all',sort:'school',source:'library',page:1});
  function clean(value) {
    const f=defaults(), v=value&&typeof value==='object'?value:{};
    for(const k of ['q','type','credits'])if(typeof v[k]==='string')f[k]=v[k].slice(0,200);
    for(const k of ['departments','years'])if(Array.isArray(v[k]))f[k]=[...new Set(v[k].filter(x=>typeof x==='string'))].slice(0,100);
    if(['all','seats','basket'].includes(v.availability))f.availability=v.availability;
    if(['school','seats','name','credits'].includes(v.sort))f.sort=v.sort;
    if(['library','current'].includes(v.source))f.source=v.source;
    if(Number.isInteger(v.page)&&v.page>0)f.page=v.page;
    return f;
  }
  const years=c=>String(c.year||'').match(/(?:19|20)\d{2}/g)||['未提供'];
  const types=c=>c.types?.length?c.types:['入口未记录'];
  function facets(courses) {
    const unique=items=>[...new Set(items)].sort((a,b)=>String(a).localeCompare(String(b),'zh-CN',{numeric:true}));
    return {types:unique(courses.flatMap(types)),departments:unique(courses.map(c=>c.school||'未提供')),
      years:unique(courses.flatMap(years)),credits:unique(courses.map(c=>c.credits==null?'未提供':String(c.credits)))};
  }
  function filter(courses,filters,chosen=[],same=()=>false) {
    const f=clean(filters), terms=f.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const result=courses.map((course,index)=>({course,index})).filter(({course:c})=> {
      const text=[c.name,c.courseCode,c.teacher,c.school,c.major,c.remarks].join(' ').toLowerCase();
      return terms.every(t=>text.includes(t)) && (!f.type||types(c).includes(f.type)) &&
        (!f.departments.length||f.departments.includes(c.school||'未提供')) &&
        (!f.years.length||years(c).some(y=>f.years.includes(y))) &&
        (!f.credits||(c.credits==null?'未提供':String(c.credits))===f.credits) &&
        (f.availability!=='seats'||c.remaining>0) &&
        (f.availability!=='basket'||chosen.some(x=>same(x,c)));
    });
    if(f.sort==='seats')result.sort((a,b)=>(b.course.remaining??-1)-(a.course.remaining??-1));
    if(f.sort==='credits')result.sort((a,b)=>(b.course.credits??-1)-(a.course.credits??-1));
    if(f.sort==='name')result.sort((a,b)=>a.course.name.localeCompare(b.course.name,'zh-CN'));
    return result;
  }
  function csv(courses) {
    const rows=courses.flatMap(c=>c.rawRows?.length?c.rawRows:[{'课程号':c.courseCode||'','课程名':c.name,'班号':c.classNo??'',
      '课程类型':types(c).join('；'),'课程类别':c.category||'','开课单位':c.school||'','学分':c.credits??'',
      '教师':c.teacher||'','年级':c.year||'','上课时间':c.schedule?.raw||'','备注':c.remarks||'','来源':'已读取选课页（非全量）'}]);
    const columns=[...new Set(rows.flatMap(r=>Object.keys(r)))];
    const cell=v=>{let s=String(v??'');if(/^[\s]*[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
    return '\ufeff'+[columns.map(cell).join(','),...rows.map(r=>columns.map(k=>cell(r[k])).join(','))].join('\r\n');
  }
  const api={defaults,clean,types,years,facets,filter,csv};root.CourseQuery=api;
  if(typeof module!=='undefined')module.exports=api;
})(globalThis);
