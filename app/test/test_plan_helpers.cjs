const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8').split('\nsetInterval(')[0];
const context = vm.createContext({CourseQuery:require('../web/course-query.js')});
vm.runInContext(source, context);
const plan = {
  courses: [{id:'sf',name:'',classNo:3}, {id:'chosen',name:'用户点选课程',school:'学院',classNo:1}],
  mutexes: [{id:'old',courses:['sf']}], delays:{sf:2},
  client:{refreshInterval:3.25,randomDeviation:.2}
};
context.prepareSelectedPlan(plan);
assert.equal(plan.courses.length, 1);
assert.equal(plan.courses[0].id, 'chosen');
assert.equal(plan.mutexes.length, 0);
assert.equal(Object.keys(plan.delays).length, 0);
assert.equal(plan.client.refreshInterval, 3.25);
context.prepareSelectedPlan(plan);
assert.equal(plan.courses.length, 1);
console.log('Selected-course preparation checks passed');
// Refresh failure must keep usable data; a different account must never inherit it.
context.fetch=async()=>{throw Error('offline fixture failure');};
vm.runInContext("renderCatalog=()=>{}; state.server={account:{maskedId:'account-a'},control:{export:{filename:'old.csv'},catalog:{}}}; state.library={courses:[{name:'cached'}],accountHint:JSON.stringify(state.server.account)};",context);
(async()=>{
  await context.loadCourseLibrary(true);
  assert.equal(vm.runInContext('state.library.courses.length',context),1);
  assert.match(vm.runInContext('state.library.error',context),/offline fixture/);
  vm.runInContext("state.server.account={maskedId:'account-b'}",context);
  await context.loadCourseLibrary(true);
  assert.equal(vm.runInContext('state.library.courses.length',context),0);
  console.log('Failed refresh retention and account isolation checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
