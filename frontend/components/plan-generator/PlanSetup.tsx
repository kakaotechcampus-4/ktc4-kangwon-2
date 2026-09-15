"use client";
import {useEffect,useState} from "react";
import {useRouter} from "next/navigation";
import {WorkspacePage,ws} from "@/components/workspace/WorkspaceUI";
import {savePlanConfig} from "@/lib/api/centers";
import {syncCenter} from "@/lib/api/onboarding";
import {loadClassSettings} from "@/lib/onboarding/settings";
import {accountStorageKey} from "@/lib/auth/demo-session";
import type {PlanConfig} from "@/lib/api/types";
export default function PlanSetup(){
 const router=useRouter(),[config,setConfig]=useState<PlanConfig>({uses_monthly:true,weekly_location:"SEPARATE_WEEKLY",safety_edu_hours:44}),[busy,setBusy]=useState(false),[error,setError]=useState("");
 useEffect(()=>{try{const raw=localStorage.getItem(accountStorageKey("saessak.planConfig"));if(raw){const c=JSON.parse(raw);if(typeof c.uses_monthly==="boolean"&&["SEPARATE_WEEKLY","DAILY_LOG_PLAN_CELL","WEEKLY_LOG_PLAN_CELL"].includes(c.weekly_location)&&Number.isFinite(c.safety_edu_hours))setConfig(c);}}catch{}},[]);
 async function save(){if(busy)return;setBusy(true);setError("");try{const settings=loadClassSettings();if(!settings)throw new Error("원 정보를 먼저 설정해주세요.");const id=await syncCenter(settings);await savePlanConfig(id,config);localStorage.setItem(accountStorageKey("saessak.planConfig"),JSON.stringify(config));router.push("/plans/start");}catch(e){setError(e instanceof Error?e.message:"저장하지 못했어요.");}finally{setBusy(false);}}
 return <WorkspacePage title="계획 문서 구성" description="우리 원에서 사용하는 계획 문서 구성을 설정해주세요."><section className={ws.card}><fieldset disabled={busy} className={ws.form}><label className={ws.check}><input type="checkbox" checked={config.uses_monthly} onChange={e=>setConfig({...config,uses_monthly:e.target.checked})}/>월간계획안 사용</label><label className={ws.field}>주간계획 위치<select value={config.weekly_location} onChange={e=>setConfig({...config,weekly_location:e.target.value as PlanConfig["weekly_location"]})}><option value="SEPARATE_WEEKLY">별도 주간계획안</option><option value="DAILY_LOG_PLAN_CELL">일일보육일지 계획란</option><option value="WEEKLY_LOG_PLAN_CELL">주간보육일지 계획란</option></select></label><label className={ws.field}>연간 안전교육 시간<input type="number" min={0} value={config.safety_edu_hours} onChange={e=>setConfig({...config,safety_edu_hours:Number(e.target.value)})}/></label><button className={ws.primary} onClick={save}>{busy?"저장 중…":"다음"}</button></fieldset>{error&&<p role="alert">{error}</p>}</section></WorkspacePage>;
}
