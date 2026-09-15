import { read, commit } from "./store";
import type { ApiClass, ClassInput } from "../../lib/api/types";

/** 예전에 저장된 age_min/age_max 레코드만 selected_ages 배열로 읽어준다(최소 fallback). */
function normalize(c: ApiClass & { age_min?: number; age_max?: number }): ApiClass {
  if (Array.isArray(c.selected_ages)) return c;
  const min = Number(c.age_min), max = Number(c.age_max);
  const ages = Number.isInteger(min) && Number.isInteger(max) && min <= max
    ? [3, 4, 5].filter(age => age >= min && age <= max)
    : [];
  return { ...c, selected_ages: ages };
}

export const findClass=(id:number)=>{const c=read().classes.find(c=>c.id===id);return c?normalize(c):undefined;};
export const listClasses=(id:number)=>read().classes.filter(c=>c.center_id===id).map(normalize);
export const addClass=(id:number,data:ClassInput)=>commit(db=>{const c={...data,selected_ages:[...data.selected_ages],child_count:data.child_count??null,id:db.next++,center_id:id};db.classes.push(c);return c;});
