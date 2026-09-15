"use client";
import Link from "next/link";
import {useEffect,useState} from "react";
import {annualContextIds} from "@/lib/plan-generator/context";
import {useWorkspace} from "@/lib/workspace/store";
import {API_STORAGE_CONTEXT} from "@/lib/api/storage-context";
import {WorkspacePage,ws} from "@/components/workspace/WorkspaceUI";
export default function PlanStart(){
 const {data}=useWorkspace(),[ids,setIds]=useState<number[]>([]);
 useEffect(()=>setIds(annualContextIds()),[]);
 const saved=[...new Set([...ids,...data.documents.filter(d=>d.annualApiSource===API_STORAGE_CONTEXT&&d.annualPlanId).map(d=>d.annualPlanId!)])];
 return <WorkspacePage title="시작 방식 선택" description="새 계획안을 만들거나 기존 계획안을 이어서 확인해주세요."><section className={ws.card}><div className={ws.actions}><Link className={ws.primary} href="/plans/annual/new">새 연간계획안 만들기</Link><Link className={ws.secondary} href="/plans/setup">문서 구성 수정</Link></div></section><h2 className="my-5 font-display text-xl">기존 계획안 이어서 보기</h2>{saved.length?<div className={ws.cards}>{saved.map(id=><Link className={ws.card} key={id} href={"/plans/annual/"+id}>{data.documents.find(d=>d.annualPlanId===id&&d.annualApiSource===API_STORAGE_CONTEXT)?.title||"연간계획안 #"+id}</Link>)}</div>:<p className={ws.hint}>아직 저장된 연간계획안이 없어요.</p>}</WorkspacePage>;
}
