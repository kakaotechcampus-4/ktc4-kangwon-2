import {redirect} from "next/navigation";
/** 레거시 주소 — 정식 주소는 /plans/annual/new(생성) · /plans/annual/{id}(결과)다. */
export default async function Page({searchParams}:{searchParams:Promise<Record<string,string|string[]|undefined>>}){
 const params=await searchParams;
 const annual=Array.isArray(params.annual)?params.annual[0]:params.annual;
 const query=new URLSearchParams();
 for(const [key,value] of Object.entries(params)){
  if(key==="annual")continue;
  if(Array.isArray(value))value.forEach(v=>query.append(key,v));
  else if(value!==undefined)query.set(key,value);
 }
 const suffix=query.size?"?"+query:"";
 redirect(annual!==undefined&&annual!==""?"/plans/annual/"+encodeURIComponent(annual)+suffix:"/plans/annual/new"+suffix);
}
