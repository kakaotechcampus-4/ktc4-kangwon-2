"use client";
import {useEffect,useState} from "react";
import {useRouter} from "next/navigation";
import AppHeader from "@/components/app/AppHeader";
import {getAnnualPlan} from "@/lib/api/plans";
import type {AnnualPlan} from "@/lib/api/types";
import {loadAnnualContext,type AnnualContext} from "@/lib/plan-generator/context";
import GenerationFlow from "./GenerationFlow";
export default function AnnualResult({id}:{id:number}){
 const router=useRouter(),[plan,setPlan]=useState<AnnualPlan|null>(null),[context,setContext]=useState<AnnualContext|undefined>(),[error,setError]=useState(""),[retry,setRetry]=useState(0);
 useEffect(()=>{const controller=new AbortController();setPlan(null);setError("");
  if(!Number.isSafeInteger(id)||id<=0){setError("올바른 계획안 주소가 아닙니다.");return;}
  setContext(loadAnnualContext(id));getAnnualPlan(id,controller.signal).then(setPlan).catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:"계획안을 불러오지 못했어요.");});
  return()=>controller.abort();
 },[id,retry]);
 const request=context?.request||{age:"mixed" as const,ageLabel:"연령 정보 없음",selectedTypes:["annual" as const],period:{annual:{year:plan?.school_year||new Date().getFullYear()},monthly:{month:3},weekly:{month:3,week:1},daily:{date:""}},memo:""};
 return <><AppHeader title="연간계획안" description="생성된 계획안을 확인하고 수정·확정해주세요." divider={false}/>
 {error?<div className="px-4 lg:px-10"><p role="alert">{error}</p><button onClick={()=>setRetry(v=>v+1)}>다시 불러오기</button></div>:!plan?<p role="status" className="px-4 lg:px-10">계획안을 불러오고 있어요.</p>:
 <GenerationFlow key={id+":"+retry} phase="done" stepIndex={4} initialConfirmed={plan.status==="CONFIRMED"} request={request}
 contents={{...context?.companions,annual:{annualPlanId:plan.id,origin:plan.months.some(m=>m.source_type==="AI")?"ai":"template",notes:[],rows:plan.months.map(m=>({label:m.month+"월",title:m.theme,detail:m.sub_themes.join("\n")}))}}}
 classId={context?.classId||""} className={context?.className||""} onBack={()=>router.push("/plans/annual/new")} onRetry={()=>router.push("/plans/annual/new")}/>}</>;
}
