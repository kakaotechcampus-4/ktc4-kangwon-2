import { read, commit } from "./store";
import type { CenterInput, PlanConfig } from "../../lib/api/types";
export const findCenter=(id:number)=>read().centers.find(c=>c.id===id);
export const addCenter=(data:CenterInput)=>commit(db=>{const c={...data,id:db.next++,created_at:new Date().toISOString()};db.centers.push(c);return c;});
export const putConfig=(id:number,data:PlanConfig)=>commit(db=>{db.configs[id]=data;return data;});
