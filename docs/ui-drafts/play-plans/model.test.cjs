const test=require('node:test');
const assert=require('node:assert/strict');
const Editor=require('./model.js');
test('all 12 months have 5+5 activities, 8 candidates, 1+1 education, blank operations and unassigned safety',()=>{
  for(let month=1;month<=12;month++){
    const m=new Editor(month),s=m.state;
    assert.equal(s.groups.together.length,5);assert.equal(s.groups.free.length,5);assert.equal(s.safetyCandidates.length,8);
    assert.ok(s.health.title&&s.nutrition.title);assert.ok(Object.values(s.safetySlots).every(x=>x===null));
    assert.ok(Object.values(s.ops).flat().every(x=>x===''));
    assert.equal(m.year,month<3?2027:2026);assert.equal(Object.keys(s.habits).length,m.weeks.length);
    assert.ok(m.restore(m.snapshot()));assert.ok(m.status().ready);
  }
});
test('canonical month boundary stays in September and February has four weeks',()=>{
  const sept=Editor.weeks(2026,9),oct=Editor.weeks(2026,10);
  assert.equal(sept.at(-1).start,'2026-09-28');assert.equal(oct[0].start,'2026-10-05');
  assert.equal(Editor.weeks(2027,2).length,4);assert.equal(Editor.weeks(2026,7).length,5);
});
test('same safety candidate can be reused and clearing one week preserves other placements',()=>{
  const m=new Editor(),[a,b]=m.weeks;const before=m.snapshot();
  m.assign('traffic',a.id);m.assign('traffic',b.id);m.assign(null,a.id);
  assert.equal(m.state.safetySlots[a.id],null);assert.equal(m.state.safetySlots[b.id],'traffic');
  assert.deepEqual(m.state.groups,before.groups);assert.deepEqual(m.state.habits,before.habits);
  assert.throws(()=>m.assign('fake',a.id));assert.throws(()=>m.assign('traffic','unknown-week'));
});
test('moving, adding and removing activity preserves stable IDs and unrelated values',()=>{
  const m=new Editor(),before=m.snapshot(),id=m.state.groups.together[0].id;
  m.move('together',id,'free',1);assert.equal(m.state.groups.free[1].id,id);
  const next=m.add('free','새 놀이');m.remove('free',next);const later=m.add('together','다음 놀이');assert.notEqual(next,later);
  assert.deepEqual(m.state.safetyCandidates,before.safetyCandidates);assert.deepEqual(m.state.ops,before.ops);
  const stable=m.snapshot();assert.throws(()=>m.move('free',id,'together',99));assert.deepEqual(m.state,stable);
});
test('educational blanks are advisory, essential play blanks block readiness',()=>{
  const m=new Editor();m.edit('health','');m.edit('nutrition','');m.edit('habits','',m.weeks[0].id);
  assert.ok(m.status().ready);assert.equal(m.status().education,2);assert.equal(m.status().habits,1);
  m.edit('theme','');assert.equal(m.status().ready,false);m.edit('theme','제목');
  for(const row of [...m.state.groups.together])m.remove('together',row.id);
  assert.equal(m.status().ready,false);
});
test('restore accepts edits and placements, rejects cross-month or corrupt state atomically',()=>{
  const m=new Editor();m.edit('family','가정에서 안내할 내용');m.assign('tools',m.weeks[2].id);
  const s=m.snapshot(),n=new Editor(7,s);assert.equal(n.restored,true);assert.deepEqual(n.state,s);
  for(const corrupt of [null,{...s,target:'2026-08'},{...s,groups:{...s.groups,free:[...s.groups.free,s.groups.free[0]]}},{...s,safetySlots:{oops:'traffic'}}]){
    const before=n.snapshot();assert.equal(n.restore(corrupt),false);assert.deepEqual(n.state,before);
  }
  const invalid=m.snapshot();invalid.groups.free[0].contentIds=['nuri2019.5.99.999'];assert.equal(n.restore(invalid),false);
});
test('habit and education choices keep their own official links and preserve other sections',()=>{
  const m=new Editor(),before=m.snapshot();m.choose('habits',6,m.weeks[0].id);m.choose('health',0);m.choose('nutrition',3);
  assert.equal(m.state.habits[m.weeks[0].id].contentId,'nuri2019.3.1.2');assert.equal(m.state.health.contentId,'nuri2019.1.2.1');
  assert.equal(m.state.nutrition.contentId,'nuri2019.1.2.2');assert.deepEqual(m.state.groups,before.groups);
  assert.throws(()=>m.choose('habits',100,m.weeks[0].id));assert.throws(()=>m.edit('__proto__','oops'));
});
test('drill choices and manual writing preserve safety and do not require a monthly drill',()=>{
  const m=new Editor(),before=m.snapshot();assert.equal(m.state.drillCandidates.length,5);
  m.chooseDrill(m.state.drillCandidates[0].id);assert.equal(m.state.ops.drill,m.state.drillCandidates[0].title);
  m.edit('drill','교사가 직접 작성한 훈련 주제');assert.equal(m.state.ops.drill,'교사가 직접 작성한 훈련 주제');
  assert.deepEqual(m.state.safetyCandidates,before.safetyCandidates);assert.deepEqual(m.state.safetySlots,before.safetySlots);
  m.edit('drill','');assert.ok(m.status().ready);assert.throws(()=>m.chooseDrill('fake'));
});
test('new drill candidates preserve the chosen teacher text and invalid responses change nothing',()=>{
  const m=new Editor();m.edit('drill','이미 작성한 내용');const rows=m.snapshot().drillCandidates;
  rows[0].title='새로 만든 훈련 후보';
  const metadata={mode:'live',model:'openai/gpt-6-luna',fingerprint:'a'.repeat(64),generatedAt:'2026-10-27T00:00:00Z'};
  m.replaceDrills(rows,metadata);assert.equal(m.state.ops.drill,'이미 작성한 내용');assert.equal(m.state.drillCandidates[0].title,rows[0].title);
  assert.equal(new Editor(7,m.snapshot()).restored,true);
  const before=m.snapshot();assert.throws(()=>m.replaceDrills(rows.slice(1),metadata));assert.deepEqual(m.state,before);
  const broken=m.snapshot();broken.drillCandidates[0].sourceIds=['fabricated'];assert.equal(m.restore(broken),false);assert.deepEqual(m.state,before);
});
test('legacy browser drafts keep all teacher values when the drill pool is added',()=>{
  const m=new Editor();m.edit('drill','기존 훈련');m.edit('family','가정연계 직접 작성');
  const saved=m.snapshot();delete saved.drillCandidates;delete saved.drillGeneration;
  const n=new Editor(7,saved);assert.ok(n.restored);assert.equal(n.state.ops.drill,'기존 훈련');assert.equal(n.state.ops.family,saved.ops.family);
  assert.equal(n.state.drillCandidates.length,5);assert.equal(n.state.drillGeneration,null);
});
test('whole monthly result applies atomically, preserves teacher operations, and leaves safety unassigned',()=>{
  const m=new Editor();m.edit('family','교사가 작성한 가정연계');m.edit('drill','교사가 작성한 훈련');m.assign('traffic',m.weeks[0].id);
  const before=m.snapshot(),result={...m.snapshot(),metadata:{mode:'live',model:'openai/gpt-6.1-sol',fingerprint:'b'.repeat(64),generatedAt:'2026-10-27T00:00:00Z'}};
  result.theme='새 7월 놀이';result.groups.free[0].title='실제 생성한 새 놀이';
  const bad=structuredClone(result);bad.groups.free[4].contentIds=['wrong'];assert.throws(()=>m.applyMonthResult(bad));assert.deepEqual(m.state,before);
  m.applyMonthResult(result);assert.equal(m.state.theme,result.theme);assert.deepEqual(m.state.ops,before.ops);
  assert.ok(Object.values(m.state.safetySlots).every(x=>x===null));assert.ok(m.state.groups.free.every(x=>!x.edited));
  assert.ok(!before.groups.free.some(x=>m.state.groups.free.some(y=>x.id===y.id)));
  assert.equal(new Editor(7,m.snapshot()).restored,true);assert.equal(m.state.monthlyGeneration.model,'openai/gpt-6.1-sol');
});

test('October descriptions stay separate from titles and survive restore with 1 to 3 links',()=>{
  const m=new Editor(10),before=m.snapshot();
  const result={...before,metadata:{mode:'live',model:'openai/gpt-6.1-sol',fingerprint:'c'.repeat(64),generatedAt:'2026-10-27T00:00:00Z'}};
  result.groups.together[0].description='투명한 통에 재료를 띄워 보는 놀이입니다.';
  result.groups.together[0].contentIds=['nuri2019.5.2.1','nuri2019.5.2.3'];
  m.applyMonthResult(result);
  const id=m.state.groups.together[0].id,title=m.state.groups.together[0].title;
  m.editDescription('together',id,'교사가 다듬은 놀이 설명');
  const n=new Editor(10,m.snapshot());assert.ok(n.restored);
  assert.equal(n.activity('together',id).description,'교사가 다듬은 놀이 설명');
  assert.equal(n.activity('together',id).title,title);
  assert.equal(n.activity('together',id).contentIds.length,2);
  const bad=structuredClone(result);bad.groups.together[0].contentIds=Array(4).fill('nuri2019.5.2.1');
  const saved=m.snapshot();assert.throws(()=>m.applyMonthResult(bad));assert.deepEqual(m.state,saved);
});
