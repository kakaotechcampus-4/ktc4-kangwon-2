(() => {
  'use strict';
  const activeModel = 'demo';
  const data = window.PLAY_PROJECT_DEMO, curriculum = window.PLAY_CURRICULUM;
  const STORAGE = 'ssemple-ui-draft-yearly-v1';
  let saved = null; try { saved = JSON.parse(localStorage.getItem(STORAGE)); } catch {}
  const model = new window.PlayEditorModel(data, curriculum, saved);
  const PERIODS = [
    {key:'m03_m05', name:'봄', label:'3~5월', months:'3월~5월'},
    {key:'m06_m08', name:'여름', label:'6~8월', months:'6월~8월'},
    {key:'m09_m11', name:'가을', label:'9~11월', months:'9월~11월'},
    {key:'m12_m02', name:'겨울', label:'12~2월', months:'12월~2월'}
  ];
  const FIELD_NAMES = {play_name:'놀이명', materials:'지원매체', support_direction:'지원 방향', learning_content_ids:'놀이를 통한 배움'};
  const view = {step:'choose', period:PERIODS[0].key, row:0, field:'support_direction', inspector:'edit', page:0, zoom:null};
  const requestedPeriod=new URLSearchParams(location.search).get('period');if(PERIODS.some(p=>p.key===requestedPeriod))view.period=requestedPeriod;
  const undo = [], redo = [];
  let typingKey = null, drag = null, toastTimer, saveTimer, detailId = null;
  document.querySelectorAll('[data-monthly-link]').forEach(link=>link.addEventListener('click',event=>{
    event.preventDefault();clearTimeout(saveTimer);
    try { localStorage.setItem(STORAGE,JSON.stringify(model.state)); }
    catch { notify('저장 공간을 확인해 주세요. 현재 편집 내용을 유지합니다.');return; }
    const month={m03_m05:3,m06_m08:7,m09_m11:10,m12_m02:12}[view.period];
    location.assign(`/monthly/?month=${month}`);
  }));
  const $ = id => document.getElementById(id);
  document.body.dataset.exampleModel = activeModel;
  document.querySelector('.prototype-pill').textContent = '디자인 검토용 · 합성 후보 40개';
  const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const periodInfo = key => PERIODS.find(p => p.key === key);
  const chosen = () => model.state.selected[view.period];
  const currentId = () => model.state.slots[view.period][view.row];
  function notify(message) { $('toast').textContent = message; $('toast').classList.add('visible'); clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').classList.remove('visible'), 2600); }
  function remember() { undo.push(model.snapshot()); if (undo.length > 30) undo.shift(); redo.length = 0; }
  function persist() {
    $('save-state').textContent = '저장 중…'; clearTimeout(saveTimer);
    saveTimer = setTimeout(() => { try { localStorage.setItem(STORAGE, JSON.stringify(model.state)); $('save-state').textContent = '이 브라우저에 저장됨'; } catch { $('save-state').textContent = '저장 공간을 확인해 주세요'; } }, 180);
    $('undo').disabled = undo.length === 0; $('redo').disabled = redo.length === 0;
  }
  function mutate(fn) {
    const before = model.snapshot();
    try { fn(); } catch (e) { model.restore(before); notify(e.message === 'FIVE_PLAYS_ONLY' ? '이 구간에서는 놀이 5개까지 고를 수 있어요.' : '같은 구간에서 선택한 놀이를 배치해 주세요.'); return false; }
    if (JSON.stringify(before) !== JSON.stringify(model.state)) { undo.push(before); if (undo.length > 30) undo.shift(); redo.length = 0; persist(); }
    typingKey = null; return true;
  }
  function learningHTML(row) {
    const groups = new Map();
    for (const id of row.learning_content_ids) { const c = model.contents[id]; if (!groups.has(c.domain)) groups.set(c.domain, []); groups.get(c.domain).push(c.text); }
    return [...groups].map(([domain, texts]) => `<strong>[${esc(domain)}]</strong><p>${texts.map(esc).join('<br>')}</p>`).join('');
  }
  function paperHTML(page, editable) {
    let html = `<section class="plan-sheet" data-page="${page}" aria-label="연간 놀이계획안 ${page+1}쪽"><h2 class="document-title">2026 연간놀이계획안 - 만4세 예시반</h2><div class="heading-spacer" aria-hidden="true"></div><table class="plan-table"><colgroup><col class="period-col"><col class="name-col"><col class="materials-col"><col class="support-col"><col class="learning-col"></colgroup><thead><tr><th scope="col">시기</th><th scope="col">놀이명</th><th scope="col">지원매체</th><th scope="col">내용 및 지원 방향 예상하기</th><th scope="col">놀이를 통한 배움</th></tr></thead><tbody>`;
    for (const p of PERIODS.slice(page * 2, page * 2 + 2)) {
      model.state.slots[p.key].forEach((id, index) => {
        html += `<tr class="doc-row" data-slot="${index}" data-period="${p.key}" ${editable && id ? `draggable="true" data-drag-id="${id}"` : ''}>`;
        if (index === 0) html += `<td class="period-cell" rowspan="5">${p.label}<small>${p.name}</small></td>`;
        if (!id) html += `<td class="empty-slot" colspan="4" ${editable ? `tabindex="0" role="button" data-empty="true" aria-label="${p.name} ${index+1}번째 빈 칸 선택"` : ''}><b>${index+1}번째 놀이</b><small>${editable ? '왼쪽에서 선택한 놀이를 끌어놓으세요' : '아직 배치하지 않은 놀이예요'}</small></td>`;
        else {
          const row = model.row(p.key, id);
          for (const [field, cls] of [['play_name','name-cell'],['materials','materials-cell'],['support_direction','support-cell'],['learning_content_ids','learning-cell']]) {
            const active = editable && p.key === view.period && index === view.row && field === view.field;
            html += `<td class="${cls}${editable ? ' editable-cell' : ''}${active ? ' active-cell' : ''}" ${editable ? `data-cell="${field}" tabindex="0" role="button" aria-label="${p.name} ${index+1}번째 ${FIELD_NAMES[field]} 편집"` : ''}>${field === 'play_name' && editable ? `<span class="row-tools">⠿ ${index+1}</span>` : ''}${field === 'learning_content_ids' ? learningHTML(row) : esc(row[field])}</td>`;
          }
        }
        html += '</tr>';
      });
    }
    return html + '</tbody></table></section>';
  }
  function renderHeader() {
    const totals = model.totals();
    document.body.dataset.step = view.step;
    $('choose-view').hidden = view.step !== 'choose'; $('edit-view').hidden = view.step !== 'edit'; $('preview-view').hidden = view.step !== 'preview';
    const headings = {choose:['함께 펼쳐 갈 놀이를 골라요','지원매체를 살펴보고, 각 구간에서 우리 반에 어울리는 놀이 5개를 골라 주세요.'],edit:['우리 반의 문서를 함께 다듬어요','왼쪽에서 내용을 편집하거나 놀이를 끌어 배치하면, 오른쪽 문서에 바로 반영돼요.'],preview:['한 해의 놀이를 한눈에 살펴봐요','배치와 편집을 마친 내용을 실제 문서 모양으로 확인해요.']};
    $('page-title').textContent = headings[view.step][0]; $('page-description').textContent = headings[view.step][1];
    document.querySelectorAll('[data-step]').forEach(el => el.setAttribute('aria-current', el.dataset.step === view.step ? 'step' : 'false'));
    $('period-tabs').innerHTML = PERIODS.map(p => `<button class="period-tab" role="tab" aria-selected="${p.key === view.period}" data-period-tab="${p.key}">${p.name}<small>${p.label} · ${model.state.selected[p.key].length}/5</small></button>`).join('');
    $('total-progress').innerHTML = `전체 <strong>${totals.selected}</strong>/20개 선택 <span>· ${totals.placed}개 배치</span>`;
    $('undo').disabled = undo.length === 0; $('redo').disabled = redo.length === 0;
  }
  function renderChoose() {
    const p = periodInfo(view.period), selected = chosen();
    $('choice-heading').textContent = `${p.name}에 함께하면 좋을 놀이 10`;
    $('candidate-grid').innerHTML = data.periods.find(x => x.period_key === p.key).rows.map((original, index) => {
      const row = model.row(p.key, original.candidate_id), isChosen = selected.includes(row.candidate_id);
      return `<article class="candidate ${isChosen ? 'selected' : ''}"><div class="card-meta"><span>PLAY ${String(index+1).padStart(2,'0')}</span>${isChosen ? '<span class="selected-label">✓ 선택한 놀이</span>' : ''}</div><h3>${esc(row.play_name)}</h3><p class="support-excerpt">${esc(row.support_direction)}</p><p class="material-line"><b>지원매체</b>${esc(row.materials)}</p><div class="card-footer"><button class="text-button" data-detail="${row.candidate_id}">자세히 살펴보기 ↗</button><button class="choose-button" data-choose="${row.candidate_id}" aria-pressed="${isChosen}">${isChosen ? '✓ 선택됨' : '+ 선택하기'}</button></div></article>`;
    }).join('');
    $('selection-count').textContent = `${selected.length}/5`; $('selection-period').textContent = `${p.name} · ${p.months}`;
    $('selected-list').innerHTML = Array.from({length:5}, (_, i) => `<li><span class="slot-badge">${i+1}</span>${selected[i] ? `<span class="summary-name">${esc(model.row(p.key,selected[i]).play_name)}</span><button class="remove-button" data-choose="${selected[i]}" aria-label="${esc(model.row(p.key,selected[i]).play_name)} 선택 해제">×</button>` : '<span class="summary-empty">우리 반의 놀이를 골라 주세요</span>'}</li>`).join('');
    $('all-periods-progress').innerHTML = PERIODS.map(x => `<div class="mini-progress"><span>${x.name} · ${x.label}</span><b>${model.state.selected[x.key].length === 5 ? '✓ 선택 완료' : `${model.state.selected[x.key].length} / 5`}</b></div>`).join('');
    $('to-editor').disabled = selected.length !== 5;
  }
  function renderPaper() { $('editor-paper').innerHTML = paperHTML(view.page, true); resizePaper(); }
  function fitScale() { return Math.min(1.6, Math.max(.35, ($('paper-canvas').clientWidth - 46) / 794)); }
  function resizePaper() {
    if (view.step !== 'edit') return;
    const scale = view.zoom || fitScale();
    $('editor-paper').style.transform = `scale(${scale})`;
    $('paper-frame').style.width = `${794 * scale}px`;
    $('paper-frame').style.height = `${Math.max(1123, $('editor-paper').offsetHeight) * scale}px`;
    $('zoom-label').textContent = `${view.zoom ? '' : '맞춤 '}${Math.round(scale * 100)}%`;
  }
  function renderEditor() {
    $('page-tabs').innerHTML = [0,1].map(i => `<button data-page-tab="${i}" class="${view.page===i?'active':''}">${i+1}쪽</button>`).join('');
    renderPaper(); renderInspector();
  }
  function renderInspector() {
    const p = periodInfo(view.period), id = currentId();
    $('pool-count').textContent = chosen().length;
    document.querySelectorAll('[data-inspector]').forEach(el => el.setAttribute('aria-selected', el.dataset.inspector === view.inspector));
    if (view.inspector === 'pool') {
      $('inspector-content').innerHTML = `<div class="edit-eyebrow">${p.name.toUpperCase()} · ${p.label}</div><h2 class="edit-title">선택한 놀이를 배치해요</h2><p class="pool-intro">카드를 <b>오른쪽 문서의 칸으로 끌어놓으세요.</b><br>드래그 대신 칸을 누르고 ‘넣기’로 배치할 수도 있어요.</p><div class="position-bar" aria-label="넣을 위치">${Array.from({length:5},(_,i)=>`<button data-target="${i}" class="${i===view.row?'active':''}" aria-label="${i+1}번째 칸에 배치">${i+1}</button>`).join('')}</div>${chosen().map(playId => { const r=model.row(p.key,playId), at=model.state.slots[p.key].indexOf(playId); return `<article class="pool-card ${at<0?'unplaced':''}" draggable="true" data-drag-id="${playId}" data-period="${p.key}"><span class="drag-handle" aria-hidden="true">⠿</span><div><h3 class="pool-name">${esc(r.play_name)}</h3><p class="pool-materials">${esc(r.materials)}</p><div class="pool-meta"><span>${at<0?'아직 배치하지 않았어요':`${at+1}번째 칸에 배치됨`}</span><button data-place="${playId}" aria-label="${esc(r.play_name)} ${view.row+1}번째 칸에 넣기">${view.row+1}번에 넣기</button></div></div></article>`; }).join('') || '<div class="empty-editor"><p>먼저 이 구간에서 놀이를 골라 주세요.</p></div>'}<button class="secondary wide" data-action="choose">놀이 선택 다시 살펴보기</button>${chosen().length ? '<button class="text-button wide" data-action="arrange">선택한 놀이를 빈 칸에 채우기</button>':''}`;
      return;
    }
    if (!id) {
      $('inspector-content').innerHTML = `<div class="edit-eyebrow">${p.name} · ${view.row+1}번째 칸</div><div class="empty-editor"><div class="empty-illustration">▦</div><h3>여기에 어떤 놀이를 놓을까요?</h3><p>선택한 놀이를 오른쪽 문서로 끌어놓으면<br>편집할 수 있는 내용이 나타나요.</p><button class="primary wide" data-action="pool">선택한 놀이 살펴보기</button></div>`;
      return;
    }
    const row = model.row(p.key,id), field = view.field;
    let form;
    if (field === 'learning_content_ids') {
      form = `<div class="form-label">놀이를 통한 배움 <span class="character-count">읽기 전용</span></div><div class="learning-selected">${learningHTML(row)}</div><p class="field-hint">표시는 누리과정 내용으로 그립니다. 연간 배움 연결 변경은 후속이므로 이 시제품에서는 편집하지 않아요.</p>`;
    } else {
      form = `<label class="form-label" for="field-value">${FIELD_NAMES[field]}<span id="character-count" class="character-count">${row[field].length}자</span></label><textarea id="field-value" class="editor-input ${field==='play_name'?'name-input':field==='support_direction'?'support-input':''}" data-edit-field="${field}" spellcheck="false">${esc(row[field])}</textarea><p class="field-hint">${field==='support_direction'?'이 놀이에서 교사가 준비하고 도울 내용을 편하게 다듬어 주세요. 수정하는 동안 문서에 바로 반영돼요.':field==='materials'?'실제로 준비할 물품을 쉼표로 나누어 적어 주세요.':'유아의 호기심이 떠오르는 이름으로 바꿔 볼 수 있어요.'}</p>`;
    }
    $('inspector-content').innerHTML = `<div class="edit-eyebrow">${p.name} · ${p.label} · ${view.row+1}번째 놀이</div><h2 class="edit-title">${esc(row.play_name || '놀이명을 입력해 주세요')}</h2><div id="teacher-status">${model.edited(p.key,id)?'<span class="teacher-badge">교사가 다듬은 내용</span>':''}</div><div class="field-tabs">${Object.entries(FIELD_NAMES).map(([key,label])=>`<button data-field-tab="${key}" class="${field===key?'active':''}">${label}</button>`).join('')}</div>${form}<div class="edit-actions"><button class="text-button" data-action="up" ${view.row===0?'disabled':''}>↑ 위로 옮기기</button><button class="text-button" data-action="down" ${view.row===4?'disabled':''}>↓ 아래로 옮기기</button></div><button class="text-button wide" data-action="unplace">문서에서 빼고 선택 목록에 두기</button>`;
  }
  function renderPreview() {
    const t = model.totals();
    $('preview-status').textContent = t.ready ? '네 구간의 놀이 20개가 모두 배치됐어요. 인쇄 전에 문장을 한 번 더 살펴봐 주세요.' : `${t.placed}/20개 배치 · ${t.selected}/20개 선택${t.incomplete ? ` · 내용을 채울 놀이 ${t.incomplete}개` : ''}`;
    $('print').disabled = !t.ready;
    $('preview-pages').innerHTML = paperHTML(0,false) + paperHTML(1,false);
  }
  function render() {
    renderHeader();
    if(view.step==='choose') renderChoose(); else if(view.step==='edit') renderEditor(); else renderPreview();
  }
  function step(name) {
    if(name==='edit' && view.step==='choose') mutate(()=>PERIODS.forEach(p=>model.arrange(p.key)));
    view.step=name; typingKey=null; render(); window.scrollTo({top:0,behavior:'instant'});
  }
  function setPeriod(key) { view.period=key; view.page=Math.floor(PERIODS.findIndex(p=>p.key===key)/2); view.row=0; typingKey=null; render(); }
  function selectCell(cell, focus=false) {
    const tr=cell.closest('[data-slot]'); if(!tr) return;
    view.period=tr.dataset.period; view.row=Number(tr.dataset.slot); view.field=cell.dataset.cell || 'play_name';
    view.inspector=cell.dataset.empty ? 'pool' : 'edit'; typingKey=null;
    renderHeader(); renderPaper(); renderInspector();
    if(focus && $('field-value')) $('field-value').focus();
  }
  function showDetail(id) {
    detailId=id; const row=model.row(view.period,id), p=periodInfo(view.period);
    $('detail-period').textContent=`${p.name} · ${p.label}`; $('detail-title').textContent=row.play_name;
    $('detail-body').innerHTML=`<div class="detail-section"><h3>제안하는 지원매체</h3><p>${esc(row.materials)}</p></div><div class="detail-section"><h3>내용 및 지원 방향</h3><p>${esc(row.support_direction)}</p></div><div class="detail-section"><h3>놀이를 통한 배움</h3><p>${esc(row.learning)}</p></div>`;
    $('detail-choose').textContent=chosen().includes(id)?'선택한 놀이에서 빼기':'이 놀이 선택하기'; $('detail-dialog').showModal();
  }
  document.addEventListener('click', event => {
    const button=event.target.closest('button');
    if(button?.dataset.step) return step(button.dataset.step);
    if(button?.dataset.periodTab) return setPeriod(button.dataset.periodTab);
    if(button?.dataset.choose) { if(mutate(()=>model.toggle(view.period,button.dataset.choose))) render(); return; }
    if(button?.dataset.detail) return showDetail(button.dataset.detail);
    if(button?.dataset.pageTab!==undefined) { view.page=Number(button.dataset.pageTab); if(Math.floor(PERIODS.findIndex(p=>p.key===view.period)/2)!==view.page) view.period=PERIODS[view.page*2].key; render(); return; }
    if(button?.dataset.inspector) { view.inspector=button.dataset.inspector; renderInspector(); return; }
    if(button?.dataset.fieldTab) { view.field=button.dataset.fieldTab; typingKey=null; renderPaper(); renderInspector(); return; }
    if(button?.dataset.target!==undefined) { view.row=Number(button.dataset.target); renderPaper(); renderInspector(); return; }
    if(button?.dataset.place) { if(mutate(()=>model.place(view.period,button.dataset.place,view.row))) { render(); notify(`${view.row+1}번째 칸에 배치했어요.`); } return; }
    if(button?.dataset.action) {
      const action=button.dataset.action;
      if(action==='choose') return step('choose');
      if(action==='pool') { view.inspector='pool'; renderInspector(); return; }
      if(action==='arrange') { mutate(()=>model.arrange(view.period)); render(); return; }
      if(action==='unplace') { mutate(()=>model.unplace(view.period,view.row)); view.inspector='pool'; render(); notify('놀이는 선택 목록에 그대로 남아 있어요.'); return; }
      if(action==='up'||action==='down') { const target=view.row+(action==='up'?-1:1); if(mutate(()=>model.place(view.period,currentId(),target))) view.row=target; render(); return; }
    }
    const cell=event.target.closest('#editor-paper [data-cell],#editor-paper [data-empty]'); if(cell) selectCell(cell);
  });
  $('editor-paper').addEventListener('keydown', event=>{ if(['Enter',' '].includes(event.key) && event.target.matches('[data-cell],[data-empty]')) { event.preventDefault(); selectCell(event.target,true); } });
  $('inspector-content').addEventListener('input', event=>{
    if(event.target.id==='curriculum-search') { const q=event.target.value.trim().toLowerCase(); document.querySelectorAll('.curriculum-option').forEach(el=>el.hidden=!el.dataset.search.toLowerCase().includes(q)); return; }
    const field=event.target.dataset.editField, id=currentId(); if(!field||!id) return;
    const key=`${view.period}:${id}:${field}`;
    if(typingKey!==key) { remember(); typingKey=key; }
    model.edit(view.period,id,field,event.target.value); persist(); renderPaper(); renderHeader();
    $('character-count').textContent=`${event.target.value.length}자`;
    $('teacher-status').innerHTML=model.edited(view.period,id)?'<span class="teacher-badge">교사가 다듬은 내용</span>':'';
    if(field==='play_name') document.querySelector('.inspector .edit-title').textContent=event.target.value || '놀이명을 입력해 주세요';
  });
  $('inspector-content').addEventListener('focusout',event=>{ if(event.target.dataset.editField) typingKey=null; });
  document.addEventListener('dragstart',event=>{
    const card=event.target.closest('[data-drag-id]'); if(!card) return;
    drag={p:card.dataset.period,id:card.dataset.dragId}; event.dataTransfer.setData('text/plain',JSON.stringify(drag)); event.dataTransfer.effectAllowed='move';
  });
  $('editor-paper').addEventListener('dragover',event=>{
    const row=event.target.closest('[data-slot]'); if(!row||!drag||row.dataset.period!==drag.p) return;
    event.preventDefault(); event.dataTransfer.dropEffect='move'; document.querySelectorAll('.drag-over').forEach(el=>el.classList.remove('drag-over')); row.classList.add('drag-over');
  });
  $('editor-paper').addEventListener('drop',event=>{
    event.preventDefault(); const row=event.target.closest('[data-slot]'); if(!row||!drag) return;
    if(row.dataset.period!==drag.p) { notify('같은 구간의 칸 안에서 옮겨 주세요.'); drag=null; return; }
    const target=Number(row.dataset.slot), {p,id}=drag; drag=null;
    if(mutate(()=>model.place(p,id,target))) { view.period=p; view.row=target; render(); notify(`${target+1}번째 칸으로 옮겼어요. 수정한 내용도 함께 이동했어요.`); }
  });
  document.addEventListener('dragend',()=>{ drag=null; document.querySelectorAll('.drag-over').forEach(el=>el.classList.remove('drag-over')); });
  $('to-editor').onclick=()=>step('edit'); $('to-preview').onclick=()=>step('preview'); $('back-to-edit').onclick=()=>step('edit');
  $('undo').onclick=()=>{ if(!undo.length)return; redo.push(model.snapshot()); model.restore(undo.pop()); typingKey=null; persist(); render(); notify('이전 상태로 되돌렸어요.'); };
  $('redo').onclick=()=>{ if(!redo.length)return; undo.push(model.snapshot()); model.restore(redo.pop()); typingKey=null; persist(); render(); };
  $('close-detail').onclick=()=>$('detail-dialog').close(); $('detail-choose').onclick=()=>{ if(mutate(()=>model.toggle(view.period,detailId))) { $('detail-dialog').close(); render(); } };
  $('expand-document').onclick=()=>{ $('large-document-pages').innerHTML=paperHTML(0,false)+paperHTML(1,false); $('large-document').showModal(); if(view.page===1) $('large-document-pages').querySelector('[data-page="1"]').scrollIntoView({block:'start'}); };
  $('close-large-document').onclick=()=>$('large-document').close();
  $('zoom-out').onclick=()=>{ view.zoom=Math.max(.4,(view.zoom||fitScale())-.1); resizePaper(); };
  $('zoom-in').onclick=()=>{ view.zoom=Math.min(1.6,(view.zoom||fitScale())+.1); resizePaper(); };
  $('zoom-fit').onclick=()=>{ view.zoom=null; resizePaper(); };
  $('print').onclick=()=>{ if(!model.totals().ready)return; renderPreview(); window.print(); };
  window.addEventListener('beforeprint',renderPreview);
  $('paper-canvas').tabIndex=0;
  $('paper-canvas').setAttribute('role','region');
  $('paper-canvas').setAttribute('aria-label','문서 스크롤 영역');
  new ResizeObserver(resizePaper).observe($('paper-canvas'));
  render();
})();
