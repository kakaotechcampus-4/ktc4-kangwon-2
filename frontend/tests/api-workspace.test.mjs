import { test } from "node:test";
import assert from "node:assert/strict";
import JSZip from "jszip";
const base = process.env.SAESSAK_TEST_URL;
async function upload(name, bytes) {
  const body = new FormData();
  body.append("file", new Blob([bytes]), name);
  return fetch(`${base}/api/templates/extract`, { method: "POST", body });
}
test("template endpoint extracts real TXT and DOCX content", { skip: !base }, async () => {
  const txt = await upload("test.txt", "놀이 주제:\n블록 놀이\n교사 지원:\n넓은 블록을 제공한다.");
  assert.equal(txt.status, 200);
  assert.ok((await txt.json()).headings.includes("교사 지원"));
  const zip = new JSZip();
  zip.file(
    "[Content_Types].xml",
    '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
  );
  zip.file(
    "_rels/.rels",
    '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
  );
  zip.file(
    "word/document.xml",
    '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>놀이 목표: 아이의 흥미를 관찰합니다.</w:t></w:r></w:p></w:body></w:document>',
  );
  const docx = await upload("test.docx", await zip.generateAsync({ type: "nodebuffer" }));
  assert.equal(docx.status, 200);
  assert.match((await docx.json()).text, /아이의 흥미/);
});
test(
  "template endpoint extracts a text PDF and rejects unsupported or empty files",
  { skip: !base },
  async () => {
    const objects = [
      "<< /Type /Catalog /Pages 2 0 R >>",
      "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
      "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
      "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ];
    const stream = "BT /F1 12 Tf 20 100 Td (Teacher observation plan test) Tj ET";
    objects.push(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
    let pdf = "%PDF-1.4\n";
    const offsets = [0];
    objects.forEach((o, i) => {
      offsets.push(Buffer.byteLength(pdf));
      pdf += `${i + 1} 0 obj\n${o}\nendobj\n`;
    });
    const xref = Buffer.byteLength(pdf);
    pdf += `xref\n0 6\n0000000000 65535 f \n${offsets
      .slice(1)
      .map((o) => `${String(o).padStart(10, "0")} 00000 n \n`)
      .join("")}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
    const response = await upload("test.pdf", pdf);
    const data = await response.json();
    assert.equal(response.status, 200, JSON.stringify(data));
    assert.match(data.text, /Teacher observation/);
    assert.equal((await upload("test.hwp", "unsupported test document")).status, 415);
    assert.equal((await upload("empty.txt", "")).status, 400);
  },
);
test("all added routes render without server failures", { skip: !base }, async () => {
  for (const path of [
    "records",
    "documents",
    "templates",
    "trends",
    "compare",
    "evaluation",
    "plans/create",
    "plans/setup",
    "plans/start",
    "plans/annual/new",
    "plans/annual/1",
  ]) {
    const response = await fetch(`${base}/${path}`);
    assert.equal(response.status, 200, path);
    const html = await response.text();
    assert.ok(!html.includes('id="__next_error__"'), path);
  }
});

/**
 * 이동 방식은 두 가지다 — next.config redirects는 HTTP 3xx + Location,
 * 서버 컴포넌트의 redirect()는 200 문서 안의 NEXT_REDIRECT 지시로 온다. 둘 다 확인한다.
 */
async function resolve(path) {
  const response = await fetch(base + path, { redirect: "manual" });
  if (response.status >= 300 && response.status < 400)
    return { via: "http", status: response.status, to: response.headers.get("location") };
  const html = await response.text();
  const marker = html.match(/NEXT_REDIRECT;(?:replace|push);([^;]+);(\d{3});/);
  if (marker) return { via: "payload", status: Number(marker[2]), to: marker[1] };
  return { via: "render", status: response.status, to: null, html };
}

test("plan routes render directly and only legacy URLs redirect", { skip: !base }, async () => {
  // 정식 주소는 redirect 없이 직접 렌더한다.
  for (const path of ["/plans/annual/new", "/plans/annual/7"]) {
    const result = await resolve(path);
    assert.equal(result.via, "render", `${path} → ${result.to}`);
    assert.equal(result.status, 200, path);
    assert.ok(!result.html.includes('id="__next_error__"'), path);
  }
  // 레거시 주소만 정식 주소로 보낸다. 쿼리는 유지하고, ?annual=은 결과 주소로 간다.
  for (const [from, to] of [
    ["/plans/create", "/plans/annual/new"],
    ["/plans/create?template=keep-me", "/plans/annual/new?template=keep-me"],
    ["/plans/create?annual=7", "/plans/annual/7"],
    ["/plans/create?annual=7&template=keep-me", "/plans/annual/7?template=keep-me"],
    ["/plan-generator?template=keep-me", "/plans/annual/new?template=keep-me"],
    ["/plans/setup", "/plans/annual/new"],
    ["/plans/start", "/plans/annual/new"],
  ]) {
    const result = await resolve(from);
    assert.equal(result.status, 307, from);
    assert.equal(result.to, to, from);
    // 목적지가 또 이동하면 loop다 — 한 번에 끝나야 한다.
    const followed = await resolve(to);
    assert.equal(followed.via, "render", `${to} → ${followed.to}`);
    assert.equal(followed.status, 200, to);
  }
});
