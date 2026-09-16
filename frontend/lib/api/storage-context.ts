/** Local ID/cache namespace only. The HTTP contract and request URLs never change. */
export const API_STORAGE_CONTEXT =
  process.env.NEXT_PUBLIC_API_MOCKING === "enabled" ? "development-mock" : "backend";
