import type { Center, ApiClass, ApiChild, AnnualPlan, PlanConfig } from "../../lib/api/types";
export interface Database { next: number; centers: Center[]; classes: ApiClass[]; children: ApiChild[]; plans: AnnualPlan[]; configs: Record<number,PlanConfig> }
const empty = (): Database => ({next:1,centers:[],classes:[],children:[],plans:[],configs:{}});
let memory = empty();
function key() { return "saessak.mswSS.v1:"+encodeURIComponent(typeof window==="undefined"?"test":sessionStorage.getItem("saessak.accountEmail")||"anonymous"); }
export function read(): Database {
  if(typeof window==="undefined") return structuredClone(memory);
  const raw=localStorage.getItem(key()); if(!raw)return empty();
  const parsed=JSON.parse(raw);
  if(!parsed || !Number.isInteger(parsed.next) || !["centers","classes","children","plans"].every(k=>Array.isArray(parsed[k])))throw new Error("Mock 저장 데이터가 손상되었습니다");
  return parsed;
}
export function commit<T>(fn:(db:Database)=>T):T {
  const db=read(),result=fn(db);
  if(typeof window==="undefined") memory=db; else localStorage.setItem(key(),JSON.stringify(db));
  return structuredClone(result);
}
export function resetTestData(){memory=empty();}
