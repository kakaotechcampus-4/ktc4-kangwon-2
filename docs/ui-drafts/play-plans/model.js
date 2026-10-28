(function (root) {
  'use strict';
  const Data = root.MonthlyData || require('./data.js');
  if(!root.PLAY_CURRICULUM&&typeof module!=='undefined')require('./curriculum.js');
  const CONTENT_IDS = new Set((root.PLAY_CURRICULUM||[]).map(c=>c.id));
  const clone = x => JSON.parse(JSON.stringify(x));
  const iso = d => d.toISOString().slice(0,10);
  function weeks(year, month) {
    const first = new Date(Date.UTC(year,month-1,1)), last = new Date(Date.UTC(year,month,0));
    const monday = new Date(first); monday.setUTCDate(first.getUTCDate()-(first.getUTCDay()+6)%7);
    const result=[];
    for (let day=monday;day<=last;day=new Date(+day+7*86400000)) {
      let inside=0;for(let i=0;i<5;i++) if(new Date(+day+i*86400000).getUTCMonth()===month-1) inside++;
      if(inside>=3) result.push({id:`${year}-${String(month).padStart(2,'0')}-W${result.length+1}`,label:`${result.length+1}주`,start:iso(day),end:iso(new Date(+day+4*86400000))});
    }
    return result;
  }
  class MonthlyEditor {
    constructor(month=7, saved=null) {
      if(!Number.isInteger(month)||month<1||month>12) throw Error('INVALID_MONTH');
      this.month=month;this.year=month<3?2027:2026;this.target=`${this.year}-${String(month).padStart(2,'0')}`;
      this.weeks=weeks(this.year,month);this.season=Data.season(month);
      this.state={version:1,target:this.target,className:'예시반',theme:this.season.theme,rationale:`${this.season.name}의 자연과 일상에서 만날 수 있는 소재를 바탕으로 다양한 놀이를 예상합니다. 유아가 선택한 방법을 존중하며, 관심이 이어지는 놀이에 자료와 공간을 더해 함께 펼쳐 갑니다.`,nextId:11,
        groups:{together:this.season.together.map(([title,id],i)=>({id:`activity-${i+1}`,title,description:'',contentIds:[id],label:'',edited:false})),free:this.season.free.map(([label,title,id],i)=>({id:`activity-${i+6}`,title,description:'',contentIds:[id],label,edited:false}))},
        safetyCandidates:clone(Data.safety),safetySlots:Object.fromEntries(this.weeks.map(w=>[w.id,null])),
        drillCandidates:clone(Data.drills),drillGeneration:null,monthlyGeneration:null,
        habits:Object.fromEntries(this.weeks.map((w,i)=>{const h=Data.habits[(i+month-3+7)%7];return [w.id,{label:h[0],title:h[1],contentId:h[2]}];})),
        health:{title:Data.health[(month-1)%4][0],contentId:Data.health[(month-1)%4][1]},nutrition:{title:Data.nutrition[(month-1)%4][0],contentId:Data.nutrition[(month-1)%4][1]},
        ops:{drill:'',characteristic:Array(5).fill(''),special:Array(5).fill(''),notice:'',birthday:'',family:''}};
      this.restored=saved?this.restore(saved):false;
    }
    snapshot(){return clone(this.state);}
    restore(raw){
      try {
        const s=clone(raw), str=x=>typeof x==='string'&&x.length<=6000;
        if(s.version!==1||s.target!==this.target||!['className','theme','rationale'].every(k=>str(s[k]))||!Number.isSafeInteger(s.nextId)||s.nextId<11)return false;
        const ids=[];
        for(const g of ['together','free']) {
          if(!Array.isArray(s.groups?.[g])||s.groups[g].length>30)return false;
          for(const x of s.groups[g]){if(x.description===undefined)x.description='';if(!/^activity-\d+$/.test(x.id)||!str(x.title)||!str(x.description)||!str(x.label)||!Array.isArray(x.contentIds)||new Set(x.contentIds).size!==x.contentIds.length||x.contentIds.some(i=>!CONTENT_IDS.has(i))||typeof x.edited!=='boolean')return false;ids.push(x.id);}
        }
        if(new Set(ids).size!==ids.length||ids.some(id=>Number(id.split('-')[1])>=s.nextId))return false;
        if(!Array.isArray(s.safetyCandidates)||s.safetyCandidates.length!==8)return false;
        for(let i=0;i<8;i++)if(!str(s.safetyCandidates[i].title)||['id','kind','label'].some(k=>s.safetyCandidates[i][k]!==Data.safety[i][k]))return false;
        for(const field of ['safetySlots','habits'])if(!s[field]||Object.keys(s[field]).length!==this.weeks.length)return false;
        for(const w of this.weeks){if(!Object.hasOwn(s.safetySlots,w.id)||s.safetySlots[w.id]!==null&&!Data.safety.some(c=>c.id===s.safetySlots[w.id]))return false;const h=s.habits[w.id];if(!h||!str(h.title)||!str(h.label)||!Data.habits.some(x=>x[2]===h.contentId))return false;}
        for(const f of ['health','nutrition'])if(!s[f]||!str(s[f].title)||!Data[f].some(x=>x[1]===s[f].contentId))return false;
        if(!s.ops||!['drill','notice','birthday','family'].every(k=>str(s.ops[k]))||!['characteristic','special'].every(k=>Array.isArray(s.ops[k])&&s.ops[k].length===5&&s.ops[k].every(str)))return false;
        // Older browser drafts predate the separate drill candidate pool.
        if(!Object.hasOwn(s,'drillCandidates')){s.drillCandidates=clone(Data.drills);s.drillGeneration=null;}
        if(!this.validDrills(s.drillCandidates)||!this.validDrillGeneration(s.drillGeneration))return false;
        if(!Object.hasOwn(s,'monthlyGeneration'))s.monthlyGeneration=null;
        if(!this.validDrillGeneration(s.monthlyGeneration))return false;
        this.state=s;return true;
      } catch{return false;}
    }
    activity(group,id){const list=this.state.groups[group];if(!list)throw Error('INVALID_GROUP');const x=list.find(x=>x.id===id);if(!x)throw Error('UNKNOWN_ACTIVITY');return x;}
    editDescription(group,id,value){if(typeof value!=='string'||value.length>6000)throw Error('INVALID_TEXT');const row=this.activity(group,id);row.description=value;row.edited=true;}
    edit(field,value,id=null,index=null){
      if(typeof value!=='string'||value.length>6000)throw Error('INVALID_TEXT');
      if(['theme','rationale','className'].includes(field))this.state[field]=value;
      else if(['together','free'].includes(field)){const x=this.activity(field,id);x.title=value;x.edited=true;}
      else if(field==='safety'){const x=this.state.safetyCandidates.find(x=>x.id===id);if(!x)throw Error('UNKNOWN_CANDIDATE');x.title=value;}
      else if(field==='habits'){if(!this.state.habits[id])throw Error('UNKNOWN_WEEK');this.state.habits[id].title=value;}
      else if(['health','nutrition'].includes(field))this.state[field].title=value;
      else if(['drill','notice','birthday','family'].includes(field))this.state.ops[field]=value;
      else if(['characteristic','special'].includes(field)&&Number.isInteger(index)&&index>=0&&index<5)this.state.ops[field][index]=value;
      else throw Error('INVALID_FIELD');
    }
    add(group,title='',contentIds=[],label=''){
      if(!['together','free'].includes(group)||this.state.groups[group].length>=30)throw Error('ACTIVITY_LIMIT');
      if(typeof title!=='string'||title.length>6000||typeof label!=='string'||!Array.isArray(contentIds)||contentIds.some(id=>!CONTENT_IDS.has(id)))throw Error('INVALID_ACTIVITY');
      const row={id:`activity-${this.state.nextId++}`,title,description:'',contentIds:[...contentIds],label,edited:true};this.state.groups[group].push(row);return row.id;
    }
    remove(group,id){this.activity(group,id);this.state.groups[group]=this.state.groups[group].filter(x=>x.id!==id);}
    move(from,id,to,index){
      const row=this.activity(from,id);if(!['together','free'].includes(to)||!Number.isInteger(index)||index<0||index>this.state.groups[to].length||from!==to&&this.state.groups[to].length>=30)throw Error('INVALID_POSITION');
      const at=this.state.groups[from].findIndex(x=>x.id===id);if(from===to&&at<index)index--;
      this.state.groups[from].splice(at,1);this.state.groups[to].splice(index,0,row);
    }
    assign(candidateId,weekId){if(!Object.hasOwn(this.state.safetySlots,weekId)||candidateId!==null&&!this.state.safetyCandidates.some(c=>c.id===candidateId))throw Error('INVALID_PLACEMENT');this.state.safetySlots[weekId]=candidateId;}
    validDrills(rows){const coreTopics=['fire_kitchen','earthquake','fire_electrical','fire_gas_leak','fire_outlet_overload','snow_ice','flood'];return Array.isArray(rows)&&rows.length===5&&new Set(rows.map(r=>r?.id)).size===5&&rows.every(r=>r&&typeof r.id==='string'&&/^drill-[a-z0-9-]{1,80}$/.test(r.id)&&typeof r.title==='string'&&r.title.trim()&&r.title.length<=240&&Array.isArray(r.sourceIds)&&r.sourceIds.length>0&&r.sourceIds.length<=5&&new Set(r.sourceIds).size===r.sourceIds.length&&r.sourceIds.every(id=>coreTopics.includes(id)||Data.drills.some(x=>x.sourceIds.includes(id))));}
    validDrillGeneration(x){return x===null||x&&['demo','live'].includes(x.mode)&&typeof x.model==='string'&&x.model.length<80&&/^[a-f0-9]{64}$/.test(x.fingerprint)&&typeof x.generatedAt==='string'&&x.generatedAt.length<40;}
    replaceDrills(rows,metadata){if(!this.validDrills(rows)||!this.validDrillGeneration(metadata)||metadata===null)throw Error('INVALID_DRILL_RESPONSE');this.state.drillCandidates=clone(rows);this.state.drillGeneration=clone(metadata);}
    chooseDrill(id){const c=this.state.drillCandidates.find(c=>c.id===id);if(!c)throw Error('UNKNOWN_DRILL');this.state.ops.drill=c.title;}
    applyMonthResult(result){
      if(result?.target!==this.target||!this.validDrillGeneration(result.metadata)||result.metadata===null)throw Error('INVALID_MONTH_RESULT');
      const next=this.snapshot(),nonblank=x=>typeof x==='string'&&x.trim()&&x.length<=6000;
      if(!nonblank(result.theme)||!nonblank(result.rationale))throw Error('INVALID_MONTH_RESULT');
      for(const g of ['together','free']){
        const rows=result.groups?.[g];if(!Array.isArray(rows)||rows.length!==5)throw Error('INVALID_MONTH_RESULT');
        next.groups[g]=rows.map(r=>{if(!nonblank(r.title)||typeof r.label!=='string'||r.description!==undefined&&typeof r.description!=='string'||!Array.isArray(r.contentIds)||r.contentIds.length<1||r.contentIds.length>3||new Set(r.contentIds).size!==r.contentIds.length||r.contentIds.some(id=>!CONTENT_IDS.has(id)))throw Error('INVALID_MONTH_RESULT');return {...clone(r),description:r.description??'',id:`activity-${next.nextId++}`,edited:false};});
      }
      next.theme=result.theme;next.rationale=result.rationale;
      next.safetyCandidates=clone(result.safetyCandidates);next.safetySlots=Object.fromEntries(this.weeks.map(w=>[w.id,null]));
      next.habits=clone(result.habits);next.health=clone(result.health);next.nutrition=clone(result.nutrition);
      next.drillCandidates=clone(result.drillCandidates);next.drillGeneration=clone(result.metadata);next.monthlyGeneration=clone(result.metadata);
      if(!this.restore(next))throw Error('INVALID_MONTH_RESULT');
    }
    choose(field,index,weekId=null){const list=field==='habits'?Data.habits:Data[field];if(!['habits','health','nutrition'].includes(field)||!Number.isInteger(index)||!list?.[index])throw Error('INVALID_CHOICE');if(field==='habits'){if(!this.state.habits[weekId])throw Error('UNKNOWN_WEEK');const [label,title,contentId]=list[index];this.state.habits[weekId]={label,title,contentId};}else{const [title,contentId]=list[index];this.state[field]={title,contentId};}}
    status(){const s=this.state,missing=[];if(!s.theme.trim())missing.push('놀이 주제');if(!s.rationale.trim())missing.push('주제선정이유');for(const [g,name]of [['together','함께 하는 활동'],['free','유아 예상 자유놀이']])if(!s.groups[g].length||s.groups[g].some(r=>!r.title.trim()))missing.push(name);
      const safety=this.weeks.filter(w=>{const c=s.safetyCandidates.find(c=>c.id===s.safetySlots[w.id]);return !c?.title.trim();}).length;
      const habits=this.weeks.filter(w=>!s.habits[w.id].title.trim()).length;
      const education=['health','nutrition'].filter(k=>!s[k].title.trim()).length;
      return {ready:!missing.length,missing,safety,habits,education};}
  }
  root.MonthlyEditor=MonthlyEditor;MonthlyEditor.weeks=weeks;
  if(typeof module!=='undefined')module.exports=MonthlyEditor;
})(globalThis);
