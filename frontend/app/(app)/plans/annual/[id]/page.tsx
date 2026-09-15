import AnnualResult from "@/components/plan-generator/AnnualResult";
export default async function Page({params}:{params:Promise<{id:string}>}){const {id}=await params;return <AnnualResult id={Number(id)}/>;}
