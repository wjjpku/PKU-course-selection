const assert=require('node:assert/strict');
const Q=require('../web/course-query.js');
const courses=[{name:'基础物理',courseCode:'00123',school:'物理学院',credits:4,year:'2025、2026',teacher:'甲',types:['专业课','通选课'],remaining:2},
  {name:'基础化学',school:'化学与分子工程学院',credits:4,year:'2026',teacher:'乙',remaining:0},
  {name:'无时间课程',school:'物理学院',credits:null,year:'',remaining:null}];
let f={...Q.defaults(),type:'专业课',departments:['物理学院'],credits:'4',years:['2026']};
assert.equal(Q.filter(courses,f).length,1);
assert.equal(Q.filter(courses,{...f,q:'物理 甲'})[0].course.courseCode,'00123');
assert.equal(Q.filter(courses,{...f,q:'物理 乙'}).length,0);
assert.equal(Q.filter(courses,{...f,type:'任选'}).length,0);
assert.equal(Q.filter(courses,{availability:'seats'}).length,1);
assert.equal(Q.filter(courses,{years:['未提供']})[0].course.name,'无时间课程');
assert.equal(Q.filter(courses,{departments:['物理学院','化学与分子工程学院']}).length,3);
assert.equal(Q.filter(courses,{availability:'basket'},[courses[1]],(a,b)=>a.name===b.name)[0].index,1);
assert.equal(Q.clean({page:-1,years:'2025',source:'evil'}).source,'library');
assert.deepEqual(Q.clean(JSON.parse(JSON.stringify(f))),f);
assert.ok(Q.facets(courses).types.includes('入口未记录'));
const csv=Q.csv([{rawRows:[{'课程名':'=1+1','课程类型':'专业课','备注':'a,"b"\nc'},{'课程名':'测试','课程类型':'通选课'}]}]);
assert.ok(csv.startsWith('\ufeff'));
assert.ok(csv.includes("'=1+1"));assert.ok(csv.includes('"a,""b""\nc"'));
assert.ok(csv.includes('通选课'));
console.log('Local query filtering, persistence normalization and CSV safety passed');
