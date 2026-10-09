/**
 * public/mockServiceWorker.js 를 NEXT_PUBLIC_API_MOCKING 값에 맞춘다.
 *
 *   enabled → msw 패키지의 워커 스크립트를 public/ 에 놓는다 (목업 사용).
 *   그 외   → public/ 에서 지운다. 실제 API 배포본에 /mockServiceWorker.js 가 남지 않는다.
 *
 * 워커는 소스가 아니라 msw 패키지에서 나오는 산출물이라 git 으로 관리하지 않는다.
 * package.json 의 predev · prebuild 가 자동으로 부른다. rm · cp 같은 OS 명령을 쓰지 않아
 * Windows 와 CI 에서 같게 동작한다.
 *
 * 사용: node scripts/msw-worker.mjs [public 디렉터리]
 */
import { copyFileSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const publicDir = process.argv[2] ?? join(root, "public");
const target = join(publicDir, "mockServiceWorker.js");
const mocking = process.env.NEXT_PUBLIC_API_MOCKING ?? "(unset)";

if (mocking === "enabled") {
  // 패키지 구조가 바뀌어도 따라가도록 exports 맵으로 찾는다.
  const source = createRequire(import.meta.url).resolve("msw/mockServiceWorker.js");
  mkdirSync(publicDir, { recursive: true });
  copyFileSync(source, target);
  console.log(`[msw-worker] copied → ${target} (mocking=${mocking})`);
} else if (existsSync(target)) {
  rmSync(target);
  console.log(`[msw-worker] removed → ${target} (mocking=${mocking})`);
} else {
  console.log(`[msw-worker] nothing to remove (mocking=${mocking})`);
}
