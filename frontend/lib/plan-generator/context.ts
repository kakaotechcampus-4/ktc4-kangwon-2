import { accountStorageKey } from "../auth/demo-session";
import { API_STORAGE_CONTEXT } from "../api/storage-context";
import type { AgeGroup, PeriodState, PlanType } from "./types";
import type { PlanContent } from "../workspace/plans";
export interface AnnualContext { request:{age:AgeGroup;ageLabel?:string;selectedTypes:PlanType[];period:PeriodState;memo:string}; classId:string;className:string;companions:Partial<Record<PlanType,PlanContent>> }
const key=()=>accountStorageKey("saessak.annualContext.v1:"+API_STORAGE_CONTEXT);
export function saveAnnualContext(id:number,value:AnnualContext){const all=readAll();all[id]=value;localStorage.setItem(key(),JSON.stringify(all));}
function readAll():Record<string,AnnualContext>{try{const raw=localStorage.getItem(key());const parsed=raw?JSON.parse(raw):{};return parsed&&typeof parsed==="object"&&!Array.isArray(parsed)?parsed:{};}catch{return {};}}
export const loadAnnualContext=(id:number)=>readAll()[id];
export const annualContextIds=()=>Object.keys(readAll()).map(Number).filter(Number.isSafeInteger);
