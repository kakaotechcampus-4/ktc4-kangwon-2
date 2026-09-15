import { read, commit } from "./store";
import type { AnnualInput, AnnualMonth, MonthInput, AnnualPlan } from "../../lib/api/types";
const themes=["새로운 우리 반","봄을 찾아요","나와 가족","우리 동네","여름 놀이","건강한 여름","함께하는 우리","가을 자연","생활 속 발견","겨울과 나눔","함께 자라요","즐거웠던 우리 반"];
export const months=():AnnualMonth[]=>[3,4,5,6,7,8,9,10,11,12,1,2].map((month,i)=>({month,theme:themes[i],sub_themes:["관심 있는 것을 찾아요","친구와 함께 표현해요"],source_type:"TEMPLATE",citation:{label:"개발용 고정 활동 자료",url:null}}));
export const findPlan=(id:number)=>read().plans.find(p=>p.id===id);
export const addPlan=(input:AnnualInput)=>commit(db=>{const plan:AnnualPlan={id:db.next++,class_id:input.class_id,school_year:input.school_year,status:"DRAFT",months:months()};db.plans.push(plan);return plan;});
export const patchMonth=(id:number,month:number,input:MonthInput)=>commit(db=>{const plan=db.plans.find(p=>p.id===id)!;const m=plan.months.find(m=>m.month===month)!;Object.assign(m,input,{source_type:"TEACHER"});return m;});
export const confirmPlan=(id:number)=>commit(db=>{db.plans.find(p=>p.id===id)!.status="CONFIRMED";return {id,status:"CONFIRMED" as const,confirmed_at:new Date().toISOString()};});
