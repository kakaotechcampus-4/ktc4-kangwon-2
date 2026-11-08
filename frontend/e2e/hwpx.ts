import { readFile } from "node:fs/promises";
import JSZip from "jszip";
import { expect, type Download } from "@playwright/test";

/**
 * 받은 한글 파일(hwpx)을 열어 본문(section0.xml)과 미리보기 글(PrvText.txt) 양쪽에
 * 기대한 글이 들어 있는지 본다. 「받아졌다」만 보면 빈 양식이나 고치기 전 내용이 나가도 통과한다.
 */
export async function verifyHwpx(file: Download, path: string, expected: string[]) {
  expect(file.suggestedFilename()).toMatch(/\.hwpx$/);
  await file.saveAs(path);
  const archive = await JSZip.loadAsync(await readFile(path));
  const section = await archive.file("Contents/section0.xml")!.async("string");
  const preview = await archive.file("Preview/PrvText.txt")!.async("string");
  for (const text of expected) {
    expect(section).toContain(text);
    expect(preview).toContain(text);
  }
}
