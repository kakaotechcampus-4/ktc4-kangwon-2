import { analyzeText } from "@/lib/workspace/model";
import { BodyLimitError, readLimitedBody } from "@/lib/workspace/api-validation";
export const runtime = "nodejs";
export async function POST(request: Request) {
  const origin = request.headers.get("origin");
  if (origin && origin !== new URL(request.url).origin)
    return Response.json({ error: "허용되지 않은 요청입니다." }, { status: 403 });
  if (Number(request.headers.get("content-length") || 0) > 6 * 1024 * 1024)
    return Response.json({ error: "5MB 이하 파일을 업로드해주세요." }, { status: 413 });
  try {
    const body = await readLimitedBody(request, 6 * 1024 * 1024);
    const form = await new Response(body, {
      headers: { "Content-Type": request.headers.get("content-type") || "" },
    }).formData();
    const file = form.get("file");
    if (!(file instanceof File) || !file.size || file.size > 5 * 1024 * 1024)
      return Response.json(
        { error: "빈 파일은 분석할 수 없어요. 5MB 이하 파일을 선택해주세요." },
        { status: 400 },
      );
    const ext = file.name.split(".").pop()?.toLowerCase();
    let text = "";
    if (ext === "txt" || ext === "md" || ext === "csv") text = await file.text();
    else if (ext === "docx") {
      const mammoth = await import("mammoth");
      text = (await mammoth.extractRawText({ buffer: Buffer.from(await file.arrayBuffer()) }))
        .value;
    } else if (ext === "pdf") {
      const { PDFParse } = await import("pdf-parse");
      const parser = new PDFParse({ data: new Uint8Array(await file.arrayBuffer()) });
      try {
        const info = await parser.getInfo();
        if (info.total > 100)
          return Response.json(
            { error: "양식은 100페이지 이하로 나누어 업로드해주세요." },
            { status: 400 },
          );
        text = (await parser.getText()).text;
      } finally {
        await parser.destroy();
      }
    } else
      return Response.json(
        {
          error:
            "PDF, DOCX, TXT, MD, CSV 파일을 지원해요. HWP/HWPX는 PDF 또는 DOCX로 내보낸 뒤 올려주세요.",
        },
        { status: 415 },
      );
    text = text.trim();
    if (text.length < 10)
      return Response.json(
        {
          error:
            "읽을 수 있는 텍스트가 부족해요. 스캔 PDF는 문자 인식 후 업로드하거나 내용을 붙여넣어주세요.",
        },
        { status: 422 },
      );
    if (text.length > 60000)
      return Response.json(
        { error: "양식 내용이 너무 길어요. 6만 자 이하로 나누어주세요." },
        { status: 413 },
      );
    return Response.json({ name: file.name, text, ...analyzeText(text) });
  } catch (error) {
    if (error instanceof BodyLimitError)
      return Response.json({ error: "5MB 이하 파일을 업로드해주세요." }, { status: 413 });
    return Response.json(
      { error: "파일을 읽지 못했어요. 암호·손상 여부를 확인하거나 텍스트를 직접 붙여넣어주세요." },
      { status: 422 },
    );
  }
}
