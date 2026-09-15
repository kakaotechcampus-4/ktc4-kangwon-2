import {redirect} from "next/navigation";
/** 구형 주소 — /plans/annual/new 로 보낸다. */
export default async function Page({searchParams}:{searchParams:Promise<Record<string,string|string[]|undefined>>}){
 const query=new URLSearchParams();
 for(const [key,value] of Object.entries(await searchParams)){
  if(Array.isArray(value))value.forEach(v=>query.append(key,v));
  else if(value!==undefined)query.set(key,value);
 }
 redirect("/plans/annual/new"+(query.size?"?"+query:""));
}
