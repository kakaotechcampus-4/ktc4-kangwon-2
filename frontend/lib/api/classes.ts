import { apiRequest } from "./client";
import type { ApiClass, ClassInput } from "./types";
export const getClasses = (centerId: number) => apiRequest<{items:ApiClass[]}>("/api/centers/"+centerId+"/classes");
export const createClass = (centerId: number, data: ClassInput) => apiRequest<ApiClass>("/api/centers/"+centerId+"/classes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
