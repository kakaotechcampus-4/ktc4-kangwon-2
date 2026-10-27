(() => {
  'use strict';
  const $=id=>document.getElementById(id), D=MonthlyData;
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const text=x=>esc(x).replace(/\n/g,'<br>');
  const contentMap=Object.fromEntries(PLAY_CURRICULUM.map(c=>[c.id,c]));
  const labels={theme:'놀이 주제',rationale:'주제선정이유',className:'반 이름',together:'함께 하는 활동',free:'유아 예상 자유놀이',habits:'기본생활습관',safety:'안전교육 후보',health:'건강교육',nutrition:'영양교육',drill:'소방대피/재난대비',characteristic:'특성화 시간표',special:'특별활동 시간표',notice:'우리반 안내사항',birthday:'우리반 생일',family:'가정연계'};
  const programs=['인성교육','수놀이','지구친구','꼬마농부 텃밭','한글놀이'],days=['월','화','수','목','금'];
  const view={tab:'edit',field:'theme',id:null,index:null,week:null,zoom:null};
  let model,undo=[],redo=[],typing=null,drag=null,toastTimer;
  const storage=month=>`ssemple-ui-draft-monthly-v1-${month}`;
  let parentContext={status:'missing',plays:[]};
  function readParentContext(){
    let saved=null;try{saved=JSON.parse(localStorage.getItem('ssemple-ui-draft-yearly-v1'));}catch{}
    parentContext=MonthlyParentBridge.read(PLAY_PROJECT_DEMO,PLAY_CURRICULUM,saved,model.month);
    model.season={...D.season(model.month),parents:parentContext.status==='ready'?parentContext.plays.map(p=>p.name):[...D.season(model.month).parents]};
    $('yearly-link').href=`/yearly/?period=${MonthlyParentBridge.periodKey(model.month)}`;
  }
  function parentSummary(){
    const linked=parentContext.status==='ready';
    const note=linked?'같은 브라우저의 연간 선택·편집 내용을 읽었어요. 아직 서비스에서 확정한 부모 계획은 아닙니다.':`연간 화면에서 이 계절의 놀이 5개를 선택해 주세요${parentContext.status==='incomplete'?` (현재 ${parentContext.count}/5개)`:''}. 아래는 화면 확인용 예시입니다.`;
    return `<details class="context-box" open><summary>${linked?'연간에서 선택한 놀이':'연간 연결 예시'} · ${model.season.months}</summary><ol>${model.season.parents.map((name,i)=>`<li>${esc(name)}${linked?`<details><summary>지원매체·지원 방향</summary><p>${esc(parentContext.plays[i].materials)}</p><p>${esc(parentContext.plays[i].support)}</p></details>`:''}<p><button class="small-button" data-action="parent-add" data-group="together" data-index="${i}">함께 하는 활동에 추가</button> <button class="small-button" data-action="parent-add" data-group="free" data-index="${i}">자유놀이에 추가</button></p></li>`).join('')}</ol><p class="parent-link-note">${esc(note)}${model.state.monthlyGeneration?' 기존 실측 초안은 생성 당시의 예시 연간을 사용했으며, 이 목록으로 자동 재생성되지 않습니다.':''}</p></details>`;
  }
  function load(month){let saved=null;try{saved=JSON.parse(localStorage.getItem(storage(month)));}catch{}model=new MonthlyEditor(month,saved);view.week=model.weeks[0].id;view.field='theme';view.id=null;view.index=null;view.tab='edit';undo=[];redo=[];typing=null;$('month').value=month;render();$('paper-canvas').scrollTop=0;$('inspector-body').scrollTop=0;if(saved&&!model.restored)notify('저장된 예시 형식을 확인할 수 없어 원본 예시를 열었어요.');}
  function notify(message){$('toast').textContent=message;$('toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('visible'),2600);}
  function persist(){try{localStorage.setItem(storage(model.month),JSON.stringify(model.state));$('save-state').textContent='이 브라우저에 저장됨';}catch{$('save-state').textContent='브라우저 저장 공간을 확인해 주세요';}$('undo').disabled=!undo.length;$('redo').disabled=!redo.length;}
  function change(fn,key=null){const before=model.snapshot();try{fn();}catch{model.restore(before);notify('배치 위치나 입력 내용을 확인해 주세요.');return false;}if(JSON.stringify(before)!==JSON.stringify(model.state)){if(!key||typing!==key){undo.push(before);if(undo.length>40)undo.shift();}redo=[];typing=key;persist();}return true;}
  function value(){const s=model.state,f=view.field;if(['together','free'].includes(f))return view.id?s.groups[f].find(r=>r.id===view.id)?.title??'':'';if(f==='safety')return s.safetyCandidates.find(c=>c.id===view.id)?.title??'';if(f==='habits')return s.habits[view.id]?.title??'';if(['health','nutrition'].includes(f))return s[f].title;if(['characteristic','special'].includes(f))return s.ops[f][view.index]??'';return Object.hasOwn(s.ops,f)?s.ops[f]:s[f]??'';}
  function active(field,id,index){return view.tab==='edit'&&view.field===field&&(id==null||view.id===id)&&(index==null||view.index===index);}
  function cell(field,body,{id=null,index=null,week=null,empty=false,readonly=false}={}){
    if(readonly)return `<div class="readonly-cell">${body||'<span class="cell-placeholder">　</span>'}</div>`;
    return `<button type="button" class="cell-edit ${active(field,id,index)?'selected':''}" data-field="${field}" ${id?`data-id="${esc(id)}"`:''} ${index!=null?`data-index="${index}"`:''} ${week?`data-week="${esc(week)}"`:''}>${body||`<span class="cell-placeholder">${empty?'교사 작성':'내용을 입력해 주세요'}</span>`}</button>`;
  }
  function paper(readonly=false){
    const s=model.state, rw={readonly};
    const activities=g=>s.groups[g].map((r,i)=>`<li class="play-item" ${readonly?'':`draggable="true" data-drag-group="${g}" data-drag-id="${r.id}" data-drop-group="${g}" data-drop-index="${i}"`}><span class="item-dot">·</span>${cell(g,`${r.label?`<span class="play-label">${esc(r.label)}) </span>`:''}${text(r.title)}`,{...rw,id:r.id})}</li>`).join('');
    let h=`<article class="sheet ${readonly?'readonly':''}" aria-label="${model.month}월 놀이계획안 문서"><h2>${model.year}년 ${model.month}월 놀이계획안</h2><table class="doc-table meta-table"><tbody><tr><th scope="row">놀이 주제</th><td colspan="3">${cell('theme',text(s.theme),rw)}</td></tr><tr><th scope="row">예상 기간</th><td>${model.year}년 ${model.month}월</td><th scope="row">만 4세</th><td>${cell('className',text(s.className),rw)}</td></tr><tr><th scope="row">주제선정이유</th><td colspan="3" class="reason-cell">${cell('rationale',text(s.rationale),rw)}</td></tr></tbody></table>`;
    h+=`<div class="section-bar">[ 예상되는 놀이 방향 ]</div><div class="play-board"><section class="play-column"><h3>함께 하는 활동</h3><ol>${activities('together')}</ol>${readonly?'':'<div class="list-drop" data-drop-group="together" data-drop-index="'+s.groups.together.length+'">놀이를 이곳으로 옮길 수 있어요</div>'}</section><div class="play-center"><small>우리의 놀이</small><strong>${text(s.theme)}</strong><span class="sprout" aria-hidden="true">✳</span></div><section class="play-column"><h3>유아 예상 자유놀이</h3><ol>${activities('free')}</ol>${readonly?'':'<div class="list-drop" data-drop-group="free" data-drop-index="'+s.groups.free.length+'">놀이를 이곳으로 옮길 수 있어요</div>'}</section></div>`;
    h+=`<table class="doc-table week-table"><thead><tr><th scope="col">구분</th>${model.weeks.map(w=>`<th scope="col">${model.month}월 ${w.label}<small>${w.start.slice(5).replace('-','.')} ~ ${w.end.slice(5).replace('-','.')}</small></th>`).join('')}</tr></thead><tbody><tr><th scope="row">기본생활습관</th>${model.weeks.map(w=>{const x=s.habits[w.id];return `<td class="habit-cell">${cell('habits',x.title?`<b>[${esc(x.label)}]</b>${text(x.title)}`:'',{...rw,id:w.id})}</td>`;}).join('')}</tr><tr><th scope="row">안전교육</th>${model.weeks.map(w=>{const c=s.safetyCandidates.find(c=>c.id===s.safetySlots[w.id]);return `<td class="safety-cell" ${readonly?'':`data-drop-week="${w.id}"`}>${cell('safety',c?`<b>[${esc(c.label)}]</b>${text(c.title)}`:readonly?'':'<span class="cell-placeholder">＋ 안전교육 배치<br>왼쪽 후보를 끌어놓으세요</span>',{...rw,id:c?.id,week:w.id})}${c&&!readonly?`<button class="remove-slot" data-action="unassign" data-week="${w.id}" aria-label="${w.label} 안전교육 비우기">×</button>`:''}</td>`;}).join('')}</tr><tr class="education-row"><th scope="row">소방대피/<br>재난대비</th><td colspan="${model.weeks.length}">${cell('drill',text(s.ops.drill),{...rw,empty:true})}</td></tr></tbody></table>`;
    h+=`<table class="doc-table education-row"><tbody><tr><th scope="row">건강‧영양교육</th><td>${cell('health',s.health.title?`<b>[건강]</b> ${text(s.health.title)}`:'',rw)}</td><td>${cell('nutrition',s.nutrition.title?`<b>[영양]</b> ${text(s.nutrition.title)}`:'',rw)}</td></tr></tbody></table>`;
    h+=`<div class="section-bar">[ 특성화 시간표 ]</div><table class="doc-table program-table"><thead><tr>${programs.map(p=>`<th scope="col">${p}</th>`).join('')}</tr></thead><tbody><tr>${programs.map((_,i)=>`<td>${cell('characteristic',text(s.ops.characteristic[i]),{...rw,index:i,empty:true})}</td>`).join('')}</tr></tbody></table>`;
    h+=`<div class="section-bar">[ 특별활동 시간표 ]</div><table class="doc-table program-table"><thead><tr>${days.map(d=>`<th scope="col">${d}</th>`).join('')}</tr></thead><tbody><tr>${days.map((_,i)=>`<td>${cell('special',text(s.ops.special[i]),{...rw,index:i,empty:true})}</td>`).join('')}</tr></tbody></table>`;
    h+=`<div class="section-bar">[ 우리반 안내사항 ]</div><table class="doc-table notice-table"><tbody>${[['notice','안내사항'],['birthday','우리반 생일'],['family','가정연계']].map(([f,label])=>`<tr><th scope="row">${label}</th><td>${cell(f,text(s.ops[f]),{...rw,empty:true})}</td></tr>`).join('')}</tbody></table><p class="doc-footer">놀이 방향은 유아의 관심에 따라 달라질 수 있습니다.</p></article>`;
    return h;
  }
  function fit(){const canvas=$('paper-canvas'),sheet=$('paper').firstElementChild;if(!sheet)return;const scale=view.zoom??Math.min(1,Math.max(.25,(canvas.clientWidth-52)/794));$('paper').style.transform=`scale(${scale})`;$('paper-frame').style.width=`${794*scale}px`;$('paper-frame').style.height=`${sheet.offsetHeight*scale}px`;$('zoom-label').textContent=view.zoom?`${Math.round(scale*100)}%`:'맞춤';}
  function renderPaper(){$('paper').innerHTML=paper();$('document-caption').textContent=`${model.year}년 ${model.month}월 놀이계획안${model.state.monthlyGeneration?' · Sol 실측 초안':''}`;requestAnimationFrame(fit);status();}
  function status(){const t=model.status(),notes=[];if(t.safety)notes.push(`안전교육 ${t.safety}주 미배치`);if(t.habits)notes.push(`생활습관 ${t.habits}주 빈칸`);if(t.education)notes.push(`건강·영양 ${t.education}칸 빈칸`);const el=$('document-status');el.textContent=t.ready?(notes.length?notes.join(' · ')+' · 안내 사항': '초안의 필수 내용이 채워졌어요'):`필수 내용 확인: ${t.missing.join(', ')}`;el.className=t.ready&&!notes.length?'good-text':'warning-text';}
  function curriculum(ids,edited=false){return `<details class="curriculum-box" open><summary>관련 누리과정 내용 <span class="badge">연계 예시</span></summary>${ids.length?ids.map(id=>{const c=contentMap[id];return c?`<p><strong>[${esc(c.domain)}] ${esc(c.category)}</strong>${esc(c.text)}</p>`:'';}).join(''):'<p>직접 추가한 놀이입니다. 누리과정 연결은 아직 설정되지 않았어요.</p>'}<p class="helper">${edited?'문장을 수정했으므로 기존 연결이 여전히 맞는지 확인해 주세요.':'놀이에서 예상되는 경험과 연결했어요. 의미가 맞는지는 교사가 확인해 주세요.'}</p></details>`;}
  function groupList(group){return `<div class="group-list">${model.state.groups[group].map((r,i)=>`<div class="group-item ${view.id===r.id?'selected':''}" draggable="true" data-drag-group="${group}" data-drag-id="${r.id}"><span class="number">${String(i+1).padStart(2,'0')}</span><button data-field="${group}" data-id="${r.id}">${esc(r.title)||'새 놀이 이름을 입력해 주세요'}</button></div>`).join('')}</div><button class="secondary" data-action="add" data-group="${group}">＋ 놀이 직접 추가</button>`;}
  function textarea(){return `<label class="field-label" for="edit-text">${esc(labels[view.field])}<span id="char-count">${value().length}자</span></label><textarea id="edit-text" class="text-input ${view.field==='rationale'?'long':value().length<40?'single':''}" maxlength="6000" spellcheck="false">${esc(value())}</textarea><p class="helper">입력하면 오른쪽 문서에 바로 반영돼요.</p>`;}
  function weekSelect(){return `<label class="field-label" for="target-week">배치할 주차</label><select id="target-week" class="form-select">${model.weeks.map(w=>`<option value="${w.id}" ${view.week===w.id?'selected':''}>${w.label} · ${w.start.slice(5)} ~ ${w.end.slice(5)}</option>`).join('')}</select>`;}
  function pool(){
    const s=model.state;
    return `<div class="edit-kicker">우리 반의 생활과 안전</div><h2 class="edit-heading">안전교육을 골라 배치해요</h2><p class="edit-hint">후보를 오른쪽 주차 칸으로 끌어놓으세요. 버튼으로도 배치할 수 있어요.</p>${weekSelect()}<p class="pool-note">한 주에 1개 · 같은 후보를 다른 주에도 쓸 수 있어요.<br>빈 주차는 안내 사항이며 초안 확인을 막지 않아요.</p>${s.safetyCandidates.map(c=>{const used=model.weeks.filter(w=>s.safetySlots[w.id]===c.id);return `<article class="pool-card ${used.length?'assigned':''}" draggable="true" data-drag-safety="${c.id}"><div class="pool-label"><span>⠿ ${esc(c.label)}</span><span>${esc(c.kind)}</span></div><h3>${esc(c.title)||'내용 미작성'}</h3><div class="pool-actions"><small>${used.length?used.map(w=>w.label).join(' · ')+' 배치':'배치 전'}</small><div><button class="small-button" data-field="safety" data-id="${c.id}">편집</button> <button class="small-button" data-action="assign" data-id="${c.id}">이 주에 배치</button></div></div></article>`;}).join('')}${parentSummary()}`;
  }
  function drillPool(){
    return `<section class="drill-pool" aria-label="소방 재난 훈련 후보"><div class="pool-section"><h3>소방·재난대비 후보 5개</h3><span>화면 예시</span></div><p class="pool-note">후보를 골라 넣거나 직접 작성하세요. 날짜·경로·집결 장소는 선생님이 정해 주세요.</p><button class="secondary drill-generate" disabled>AI 후보 생성 · API 연결 전</button><p class="helper">디자인 확인용 예시입니다. 유료 호출·법정 충족 검사는 하지 않습니다.</p>${model.state.drillCandidates.map(c=>`<article class="pool-card drill-card"><h3>${esc(c.title)}</h3><div class="pool-actions"><small>예시 주제 · 실시 기록 아님</small><button class="small-button" data-action="choose-drill" data-id="${esc(c.id)}">문서에 넣기</button></div></article>`).join('')}</section>`;
  }
  function renderInspector(){
    $('tab-edit').setAttribute('aria-selected',view.tab==='edit');$('tab-pool').setAttribute('aria-selected',view.tab==='pool');
    document.querySelectorAll('[data-jump]').forEach(b=>b.classList.toggle('active',b.dataset.jump===view.field||b.dataset.jump==='habits'&&['safety','health','nutrition'].includes(view.field)||b.dataset.jump==='drill'&&['drill','characteristic','special','notice','birthday','family'].includes(view.field)));
    if(view.tab==='pool'){$('inspector-body').innerHTML=pool();return;}
    const f=view.field,s=model.state;
    let h=`<div class="edit-kicker">${['drill','characteristic','special','notice','birthday','family'].includes(f)?'선생님이 채우는 정보':'문서를 보며 다듬어요'}</div><h2 class="edit-heading">${esc(labels[f])}</h2><p class="edit-hint">${f==='habits'?`${model.weeks.find(w=>w.id===view.id)?.label??''}의 생활 속 작은 실천을 골라요.`:['drill','characteristic','special','notice','birthday','family'].includes(f)?'실제로 정한 내용을 적어 주세요. 비워 두어도 초안 확인이 가능해요.':'오른쪽 문서에서 다른 칸을 눌러 편집할 수 있어요.'}</p>`;
    if(['together','free'].includes(f)){
      const row=s.groups[f].find(r=>r.id===view.id);
      if(row){const at=s.groups[f].indexOf(row);h+=textarea()+`<label class="field-label" for="edit-description">놀이 설명 <span class="badge">편집 화면 전용</span></label><textarea id="edit-description" class="text-input long" maxlength="6000" spellcheck="false">${esc(row.description??'')}</textarea><p class="helper">어떤 재료로 무엇을 해 볼 수 있는지 확인해요. 설명은 문서·인쇄에 나오지 않아요. 재료는 준비 제안입니다.</p><div class="editor-actions"><button class="small-button" data-action="up" ${at===0?'disabled':''}>↑ 위로</button><button class="small-button" data-action="down" ${at===s.groups[f].length-1?'disabled':''}>↓ 아래로</button><span class="spacer"></span><button class="small-button danger" data-action="delete">놀이 삭제</button></div>`+curriculum(row.contentIds,row.edited);}
      h+=groupList(f);
    } else if(f==='safety'){
      h+=textarea()+weekSelect()+`<button class="primary" data-action="assign" data-id="${esc(view.id)}">선택한 주에 배치</button><p class="helper">주차 배치와 후보 내용은 따로 보존돼요. 후보 내용을 고치면 같은 후보를 배치한 주에도 반영돼요.</p><div class="editor-actions"><button class="secondary" data-action="open-pool">← 후보 8개 보기</button></div>`;
    } else if(['habits','health','nutrition'].includes(f)){
      const opts=f==='habits'?D.habits:D[f];
      h+=`<label class="field-label" for="education-choice">다른 제안 고르기</label><select id="education-choice" class="form-select"><option value="">현재 내용 유지</option>${opts.map((x,i)=>`<option value="${i}">${esc(f==='habits'?`[${x[0]}] ${x[1]}`:x[0])}</option>`).join('')}</select>`+textarea()+curriculum([f==='habits'?s.habits[view.id].contentId:s[f].contentId])+`<p class="helper">내용을 비우면 안내가 표시되지만 초안 확인을 막지는 않아요.</p>`;
    } else {
      if(['characteristic','special'].includes(f))h+=`<span class="subtle-tag">${esc(f==='characteristic'?programs[view.index]:days[view.index]+'요일')}</span>`;
      h+=textarea();
      if(f==='drill')h+=drillPool();
      if(f==='theme'||f==='rationale')h+=parentSummary();
    }
    $('inspector-body').innerHTML=h;
  }
  function render(){readParentContext();renderInspector();renderPaper();persist();}
  function select(field,id=null,index=null,week=null){typing=null;view.field=field;view.id=id;view.index=index;
    if(field==='habits'&&!id)view.id=model.weeks[0].id;
    if(['special','characteristic'].includes(field)&&index==null)view.index=0;
    if(week)view.week=week;
    if(field==='safety'&&!id)view.tab='pool';else view.tab='edit';
    renderInspector();renderPaper();$('inspector-body').scrollTop=0;
  }
  function applyCandidate(id){if(change(()=>model.assign(id,view.week))) {render();notify(`${model.weeks.find(w=>w.id===view.week).label}에 배치했어요.`);}}
  function openPreview(){const t=model.status(),notes=[];if(t.safety)notes.push(`안전교육 ${t.safety}주 미배치`);if(t.habits)notes.push(`생활습관 ${t.habits}주 빈칸`);if(t.education)notes.push(`건강·영양 ${t.education}칸 빈칸`);$('preview-paper').innerHTML=paper(true);$('preview-title').textContent=`${model.year}년 ${model.month}월 놀이계획안`;$('preview-status').textContent=t.ready?`전체 초안을 확인해 주세요.${notes.length?' '+notes.join(' · ')+' (안내)':''}`:`인쇄 전 ${t.missing.join(', ')} 내용을 채워 주세요.`;$('print').disabled=!t.ready;$('preview-dialog').showModal();}
  document.addEventListener('click',event=>{
    const b=event.target.closest('button');if(!b)return;
    if(b.dataset.field){select(b.dataset.field,b.dataset.id??null,b.dataset.index!=null?Number(b.dataset.index):null,b.dataset.week??null);return;}
    if(b.dataset.jump){select(b.dataset.jump);const target=$('paper').querySelector(`[data-field="${b.dataset.jump}"]`);if(target){const c=$('paper-canvas'),r=target.getBoundingClientRect(),cr=c.getBoundingClientRect();if(b.dataset.jump==='theme')c.scrollTop=0;else c.scrollTop+=r.top-cr.top-30;}return;}
    const a=b.dataset.action;if(!a)return;
    if(a==='assign')applyCandidate(b.dataset.id);
    else if(a==='choose-drill'){if(value().trim()&&view.field==='drill'&&value()!==model.state.drillCandidates.find(c=>c.id===b.dataset.id)?.title){pendingDrill=b.dataset.id;$('replace-drill-dialog').showModal();}else{change(()=>model.chooseDrill(b.dataset.id));render();notify('훈련 주제를 문서에 넣었어요. 직접 수정할 수 있어요.');}}
    else if(a==='unassign'){change(()=>model.assign(null,b.dataset.week));render();}
    else if(a==='open-pool'){view.tab='pool';renderInspector();}
    else if(a==='add'){let id;if(change(()=>{id=model.add(b.dataset.group);}))select(b.dataset.group,id);$('edit-text')?.focus();}
    else if(a==='parent-add'){let id;if(change(()=>{id=model.add(b.dataset.group,model.season.parents[Number(b.dataset.index)]);}))select(b.dataset.group,id);}
    else if(a==='delete'){const g=view.field;change(()=>model.remove(g,view.id));select(g);}
    else if(a==='up'||a==='down'){const g=view.field,at=model.state.groups[g].findIndex(x=>x.id===view.id);change(()=>model.move(g,view.id,g,a==='up'?at-1:at+2));render();}
  });
  $('inspector-body').addEventListener('input',e=>{if(e.target.id==='edit-description'){if(change(()=>model.editDescription(view.field,view.id,e.target.value),`${view.field}/${view.id}/description`))renderPaper();return;}if(e.target.id!=='edit-text')return;const key=`${view.field}/${view.id}/${view.index}`;if(change(()=>model.edit(view.field,e.target.value,view.id,view.index),key)){$('char-count').textContent=`${e.target.value.length}자`;renderPaper();}});
  $('inspector-body').addEventListener('focusout',e=>{if(['edit-text','edit-description'].includes(e.target.id))typing=null;});
  $('inspector-body').addEventListener('change',e=>{if(e.target.id==='target-week')view.week=e.target.value;if(e.target.id==='education-choice'&&e.target.value!==''){change(()=>model.choose(view.field,Number(e.target.value),view.id));render();}});
  $('tab-edit').onclick=()=>{if(view.field==='safety'&&!view.id)view.field='theme';view.tab='edit';renderInspector();};$('tab-pool').onclick=()=>{view.tab='pool';renderInspector();};
  $('undo').onclick=()=>{if(!undo.length)return;redo.push(model.snapshot());model.restore(undo.pop());typing=null;repairSelection();render();};
  $('redo').onclick=()=>{if(!redo.length)return;undo.push(model.snapshot());model.restore(redo.pop());typing=null;repairSelection();render();};
  function repairSelection(){if(['together','free'].includes(view.field)&&!model.state.groups[view.field].some(r=>r.id===view.id))view.id=null;}
  $('preview').onclick=openPreview;$('expand').onclick=openPreview;$('close-preview').onclick=()=>$('preview-dialog').close();
  $('print').onclick=()=>{if(!model.status().ready){notify('필수 놀이 내용을 먼저 채워 주세요.');return;}document.fonts.ready.then(()=>window.print());};
  $('reset').onclick=()=>$('reset-dialog').showModal();$('cancel-reset').onclick=()=>$('reset-dialog').close();$('confirm-reset').onclick=()=>{const before=model.snapshot();model=new MonthlyEditor(model.month);undo.push(before);redo=[];typing=null;view.field='theme';view.tab='edit';view.id=null;$('reset-dialog').close();render();notify('현재 월의 예시를 다시 열었어요. 되돌리기로 복원할 수 있어요.');};
  let pendingDrill=null;
  $('cancel-drill-replace').onclick=()=>{pendingDrill=null;$('replace-drill-dialog').close();};
  $('confirm-drill-replace').onclick=()=>{if(pendingDrill){change(()=>model.chooseDrill(pendingDrill));render();}pendingDrill=null;$('replace-drill-dialog').close();};

  $('month').innerHTML=[3,4,5,6,7,8,9,10,11,12,1,2].map(m=>`<option value="${m}">${m<3?'2027':'2026'}년 ${m}월</option>`).join('');$('month').onchange=e=>load(Number(e.target.value));
  $('zoom-fit').onclick=()=>{view.zoom=null;fit();};$('zoom-in').onclick=()=>{view.zoom=Math.min(1.6,(view.zoom??Math.min(1,($('paper-canvas').clientWidth-52)/794))+.1);fit();};$('zoom-out').onclick=()=>{view.zoom=Math.max(.3,(view.zoom??Math.min(1,($('paper-canvas').clientWidth-52)/794))-.1);fit();};
  new ResizeObserver(fit).observe($('paper-canvas'));document.fonts.ready.then(fit);
  document.addEventListener('dragstart',e=>{const row=e.target.closest('[draggable=true]');if(!row)return;drag=row.dataset.dragSafety?{kind:'safety',id:row.dataset.dragSafety}:row.dataset.dragParent!=null?{kind:'parent',index:Number(row.dataset.dragParent)}:{kind:'activity',group:row.dataset.dragGroup,id:row.dataset.dragId};e.dataTransfer.effectAllowed=drag.kind==='activity'?'move':'copy';e.dataTransfer.setData('text/plain',JSON.stringify(drag));});
  document.addEventListener('dragover',e=>{const target=e.target.closest('[data-drop-week],[data-drop-group]');if(!target||!drag)return;if(drag.kind==='safety'?!target.dataset.dropWeek:!target.dataset.dropGroup)return;e.preventDefault();target.classList.add('drop-over');});
  document.addEventListener('dragleave',e=>{const x=e.target.closest('.drop-over');if(x&&!x.contains(e.relatedTarget))x.classList.remove('drop-over');});
  document.addEventListener('drop',e=>{const target=e.target.closest('[data-drop-week],[data-drop-group]');document.querySelectorAll('.drop-over').forEach(x=>x.classList.remove('drop-over'));if(!target||!drag)return;e.preventDefault();
    if(drag.kind==='safety'&&target.dataset.dropWeek){view.week=target.dataset.dropWeek;applyCandidate(drag.id);}
    else if(target.dataset.dropGroup&&drag.kind==='activity'){const g=target.dataset.dropGroup;if(change(()=>model.move(drag.group,drag.id,g,Number(target.dataset.dropIndex))))select(g,drag.id);}
    else if(target.dataset.dropGroup&&drag.kind==='parent'){const g=target.dataset.dropGroup;let id;if(change(()=>{id=model.add(g,model.season.parents[drag.index]);model.move(g,id,g,Number(target.dataset.dropIndex));}))select(g,id);}
    drag=null;
  });
  document.addEventListener('dragend',()=>{drag=null;document.querySelectorAll('.drop-over').forEach(x=>x.classList.remove('drop-over'));});
  const requestedMonth=Number(new URLSearchParams(location.search).get('month'));load(Number.isInteger(requestedMonth)&&requestedMonth>=1&&requestedMonth<=12?requestedMonth:7);
  $('connection-state').textContent='디자인 DRAFT · API 연결 없음';
})();
