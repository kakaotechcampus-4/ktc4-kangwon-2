"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { DOCUMENT_KINDS, today, validPeriod, compareEvidence, invalidateDependents, assertDocumentUnchanged, type DocumentKind, type SavedDocument, type Source, type Section } from "@/lib/workspace/model";
import { useWorkspace } from "@/lib/workspace/store";
import { requestAI } from "@/lib/workspace/ai-client";
import DocumentEditor from "./DocumentEditor";
import { WorkspacePage, Empty, Message, useClasses, useAIStatus, AIHint, ws } from "./WorkspaceUI";

export default function DocumentsPage() {
  const {data,ready,error,blocked,save} = useWorkspace(); const classes=useClasses(); const available=useAIStatus();
  const [mode,setMode]=useState<"library"|"create">("library"); const [active,setActive]=useState(""); const [kind,setKind]=useState<DocumentKind>("observation");
  const [classId,setClassId]=useState("");const [childId,setChildId]=useState("");const [start,setStart]=useState(today);const [end,setEnd]=useState(today);
  const [selected,setSelected]=useState<string[]>([]);const [busy,setBusy]=useState(false);const [message,setMessage]=useState("");const [search,setSearch]=useState("");const [filter,setFilter]=useState("all");
  useEffect(()=>{if(!ready)return;const id=new URLSearchParams(window.location.search).get("record");const record=data.observations.find(r=>r.id===id);if(record){setMode("create");setClassId(record.classId);setChildId(record.childId);setStart(record.date);setEnd(record.date);setSelected([record.id]);} },[ready]);
  const classroom=classes.find(c=>c.id===classId);const child=classroom?.children.find(c=>c.id===childId);
  const candidates: Source[] = kind==="weeklyLog" ? data.documents.filter(d=>d.kind==="dailyLog" && d.status==="confirmed" && d.sections.some(s=>s.heading==="사실") && d.classId===classId && (!childId || d.childId===childId) && d.start>=start && d.end<=end).map(d=>({id:d.id,date:d.start,text:d.sections.filter(s=>s.heading==="사실").map(s=>s.body).join("\n\n"),childId:d.childId,classId:d.classId})) : data.observations.filter(r=>r.classId===classId && (!childId || r.childId===childId) && r.date>=start && r.date<=end).map(r=>({id:r.id,date:r.date,text:r.fact,childId:r.childId,classId:r.classId}));
  const sources=candidates.filter(s=>selected.includes(s.id));
  const documents=data.documents.filter(d=>(filter==="all" || d.status===filter) && `${d.title} ${d.childName} ${d.className}`.includes(search)).sort((a,b)=>b.updatedAt.localeCompare(a.updatedAt));
  const current=data.documents.find(d=>d.id===active);
  async function generate(ai:boolean){
    if(busy || available===null || !classroom || !validPeriod(start,end) || !sources.length || ((kind==="observation"||kind==="assessment")&&!child) || (kind==="dailyLog" && start!==end)){setMessage("반·아동·기간·근거 기록을 확인해주세요. 일일 보육일지는 같은 날짜로 설정해주세요.");return;}
    setBusy(true);setMessage("");
    try {
      const title=`${child?.name || classroom.className} ${DOCUMENT_KINDS[kind]} · ${start}`;
      let sections:Section[]=[{heading:"해석",body:"",sourceIds:sources.map(s=>s.id)},{heading:"지원",body:"",sourceIds:sources.map(s=>s.id)}];
      if(ai){const result=await requestAI<{sections:Section[]}>("document",{kind:DOCUMENT_KINDS[kind],start,end,sources});sections=result.sections.filter(s=>s.heading==="해석"||s.heading==="지원");if(sections.length!==2||!sections.some(s=>s.heading==="해석")||!sections.some(s=>s.heading==="지원"))throw new Error("AI가 필수 항목을 완성하지 못했어요. 다시 생성해주세요.");}
      const timestamp=new Date().toISOString();const doc:SavedDocument={id:crypto.randomUUID(),title,kind,classId,className:classroom.className,childId,childName:child?.name||"",start,end,sources,sections:[{heading:"사실",body:sources.map(s=>s.text).join("\n\n"),sourceIds:sources.map(s=>s.id)},...sections],status:"draft",origin:ai?"ai":"teacher",createdAt:timestamp,updatedAt:timestamp,reviewNote:"교사 검토 전"};
      if(save(prev=>({...prev,documents:[doc,...prev.documents]}))){setActive(doc.id);setMode("library");setMessage("원본 사실을 담은 초안을 만들었어요. 해석과 지원을 검토해주세요.");}
    }catch(e){setMessage(e instanceof Error?e.message:"초안 생성에 실패했어요.");}finally{setBusy(false);}
  }
  return <WorkspacePage title="문서 보관함" description="기록에서 시작해, 선생님의 검토로 완성되는 우리 반 문서.">
    <div className={ws.hero}><div><div className={ws.eyebrow}>DOCUMENTS · 기록을 의미 있는 문서로</div><h2>사실은 그대로, 지원은 구체적으로.</h2><p>일일·주간 보육일지부터 관찰일지와 영유아 평가까지 한곳에서 관리해요.</p></div><button className={ws.primary} onClick={()=>{setMode(mode==="create"?"library":"create");setMessage("");}}>{mode==="create"?"보관함 보기":"＋ 기록으로 문서 만들기"}</button></div>
    <Message error>{error}</Message><Message>{message}</Message>
    {mode==="create" ? <div className={ws.grid}><section className={ws.card}><h2>문서 작성 조건</h2><AIHint available={available}/><div className={ws.form}>
      <label className={ws.field}>문서 종류<select disabled={busy} value={kind} onChange={e=>{setKind(e.target.value as DocumentKind);setSelected([]);}}>{(["dailyLog","weeklyLog","observation","assessment"] as DocumentKind[]).map(k=><option key={k} value={k}>{DOCUMENT_KINDS[k]}</option>)}</select></label>
      <div className={ws.row}><label className={ws.field}>담당 반<select disabled={busy} value={classId} onChange={e=>{setClassId(e.target.value);setChildId("");setSelected([]);}}><option value="">반 선택</option>{classes.map(c=><option key={c.id} value={c.id}>{c.className||"이름 없는 반"}</option>)}</select></label><label className={ws.field}>대상 아동<select disabled={busy} value={childId} onChange={e=>{setChildId(e.target.value);setSelected([]);}}><option value="">반 전체</option>{classroom?.children.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label></div>
      <div className={ws.row}><label className={ws.field}>시작일<input disabled={busy} type="date" value={start} onChange={e=>{setStart(e.target.value);setSelected([]);}}/></label><label className={ws.field}>종료일<input disabled={busy} type="date" value={end} onChange={e=>{setEnd(e.target.value);setSelected([]);}}/></label></div>
      <p className={ws.hint}>{kind==="weeklyLog"?"주간 보육일지는 검토가 완료된 일일 보육일지만 근거로 사용해요.":kind==="assessment"?"한 아동의 누적 관찰을 선택해주세요. 기록에 드러난 변화만 다루며 발달을 진단하지 않아요.":"관찰일지는 아동을 선택하고, 일일 보육일지는 시작·종료일을 같은 날짜로 지정해주세요."}</p>
      <button className={ws.primary} disabled={busy||available===null||!sources.length||blocked} onClick={()=>generate(available===true)}>{busy?"초안 작성 중…":available?"AI 초안 생성":"원본으로 초안 만들기"}</button><Link className={ws.link} href="/records">새 관찰 기록 입력 →</Link>
    </div></section><section className={ws.card}><div className={ws.between}><h2>문서에 사용할 근거</h2><span className={ws.badge}>{sources.length}건 선택</span></div><p className={ws.hint}>선택한 반·아동·기간의 기록만 표시됩니다.</p>{!candidates.length?<Empty title="조건에 맞는 근거가 없어요">날짜를 변경하거나 {kind==="weeklyLog"?"일일 보육일지를 먼저 작성하고 확정해주세요.":"관찰 기록을 먼저 입력해주세요."}</Empty>:<><button disabled={busy} className={ws.secondary} onClick={()=>setSelected(sources.length===candidates.length?[]:candidates.map(s=>s.id))}>{sources.length===candidates.length?"선택 해제":"모두 선택"}</button><div className={ws.scroll}>{candidates.map(s=><label key={s.id} className={ws.check}><input type="checkbox" disabled={busy} checked={selected.includes(s.id)} onChange={e=>setSelected(prev=>e.target.checked?[...prev,s.id]:prev.filter(id=>id!==s.id))}/><span><b>{s.date}</b><small>{s.text}</small></span></label>)}</div></>}</section></div> : <>
      <div className={ws.between}><div className={ws.pills}>{[["all","전체"],["draft","검토 중"],["confirmed","확정"]].map(([id,label])=><button key={id} aria-pressed={filter===id} className={filter===id?ws.selected:undefined} onClick={()=>setFilter(id)}>{label} {data.documents.filter(d=>id==="all"||d.status===id).length}</button>)}</div><Link className={ws.link} href="/evaluation">평가제·증빙 점검 →</Link></div><input className={ws.input} style={{margin:"17px 0"}} aria-label="문서 검색" placeholder="문서 제목, 반, 아동으로 검색" value={search} onChange={e=>setSearch(e.target.value)}/>
      {!documents.length?<Empty title="보관된 문서가 없어요">관찰 기록으로 첫 문서를 만들어보세요.</Empty>:<div className={ws.grid}><div className={ws.list}>{documents.map(d=><button key={d.id} className={`${ws.item} ${active===d.id?ws.selected:""}`} onClick={()=>{setActive(d.id);setMessage("");}}><div className={ws.between}><span className={ws.badge}>{d.status==="confirmed"?"확정":"검토 중"}</span><span className={ws.muted}>{d.start}</span></div><h3 style={{marginTop:13}}>{d.title}</h3><p className={ws.muted}>{d.className} · {DOCUMENT_KINDS[d.kind]} · 근거 {d.sources.length}건</p></button>)}</div>{current?<DocumentEditor key={current.id} initial={current} onSave={(doc,expected)=>save(prev=>{assertDocumentUnchanged(prev.documents.find(d=>d.id===doc.id),expected);if(doc.status==="confirmed" && compareEvidence(doc,prev.documents,prev.observations).linked.some(r=>r.state!=="일치"))throw new Error("원본이 변경되었거나 없어졌어요. 최신 기록으로 초안을 다시 생성해주세요.");return {...prev,documents:invalidateDependents(prev.documents.map(d=>d.id===doc.id?doc:d),doc.id)};})}/>:<Empty title="확인할 문서를 선택해주세요">초안을 수정하고 원본과 대조한 후 확정할 수 있어요.</Empty>}</div>}
    </>}
  </WorkspacePage>;
}
