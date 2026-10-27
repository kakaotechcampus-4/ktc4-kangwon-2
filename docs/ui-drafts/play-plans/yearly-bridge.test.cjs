const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const Model=require('./yearly/model.js'),Bridge=require('./yearly-bridge.js');
const context={};context.window=context;
for(const name of ['../data.js','demo-candidates.js','../curriculum.js'])vm.runInNewContext(fs.readFileSync(__dirname+'/yearly/'+name,'utf8'),context);
const data=context.PLAY_PROJECT_DEMO,curriculum=context.PLAY_CURRICULUM;
function chosen(){const m=new Model(data,curriculum);for(let i=1;i<=5;i++)m.toggle('m09_m11','cand'+i);return m;}

test('all months resolve the shared yearly season, including January and February',()=>{
  assert.deepEqual(Array.from({length:12},(_,i)=>Bridge.periodKey(i+1)),['m12_m02','m12_m02','m03_m05','m03_m05','m03_m05','m06_m08','m06_m08','m06_m08','m09_m11','m09_m11','m09_m11','m12_m02']);
  assert.throws(()=>Bridge.periodKey(13));
});
test('five selected plays preserve document order and teacher edits in monthly context',()=>{
  const m=chosen();m.arrange('m09_m11');m.place('m09_m11','cand5',0);m.edit('m09_m11','cand5','materials','교사가 정한 재료');
  const saved=m.snapshot(),before=JSON.stringify(saved),r=Bridge.read(data,curriculum,saved,10);
  assert.equal(r.status,'ready');assert.equal(r.plays.length,5);assert.equal(r.plays[0].id,'cand5');assert.equal(r.plays[0].materials,'교사가 정한 재료');
  assert.ok(r.plays.every(p=>p.name&&p.support&&p.contentIds.length>=2));assert.equal(JSON.stringify(saved),before);
});
test('a seasonal choice is shared by all three months and not consumed',()=>{
  const saved=chosen().snapshot();
  assert.deepEqual(Bridge.read(data,curriculum,saved,9).plays,Bridge.read(data,curriculum,saved,10).plays);
  assert.deepEqual(Bridge.read(data,curriculum,saved,10).plays,Bridge.read(data,curriculum,saved,11).plays);
});
test('missing or partial selection never silently chooses five candidates',()=>{
  assert.equal(Bridge.read(data,curriculum,null,10).status,'missing');
  const m=chosen();m.toggle('m09_m11','cand5');const r=Bridge.read(data,curriculum,m.snapshot(),10);
  assert.equal(r.status,'incomplete');assert.equal(r.count,4);assert.deepEqual(r.plays,[]);
});
test('different model data and malformed storage cannot become a parent selection',()=>{
  const saved=chosen().snapshot();assert.equal(Bridge.read({...data,run_id:'another-fixture'},curriculum,saved,10).status,'invalid');
  saved.edits['m09_m11:cand1']={learning_content_ids:null};assert.equal(Bridge.read(data,curriculum,saved,10).status,'invalid');
});
