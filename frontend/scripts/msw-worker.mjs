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
 * 사용: node scripts/msw-worker.mjs [--dev] [프로젝트 디렉터리]
 *   --dev          predev 쪽. next dev 와 같은 .env 파일을 본다.
 *   프로젝트 디렉터리  생략하면 이 스크립트가 들어 있는 frontend/ 를 쓴다.
 */
import { copyFileSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);

const args = process.argv.slice(2);
const dev = args.includes("--dev");
const here = dirname(dirname(fileURLToPath(import.meta.url)));
const projectDir = resolve(args.find((arg) => !arg.startsWith("--")) ?? here);
const publicDir = join(projectDir, "public");
const target = join(publicDir, "mockServiceWorker.js");

/**
 * npm 의 predev 는 next 보다 먼저 돈다. 여기서 .env 파일을 직접 읽지 않으면
 * .env.local 에 NEXT_PUBLIC_API_MOCKING=enabled 를 적어두고 npm run dev 를 해도
 * 이 스크립트에는 값이 비어 보여서, 방금 쓰려던 워커 파일을 도로 지워버린다.
 *
 * 그래서 next 가 쓰는 @next/env 를 그대로 쓴다. 읽는 파일과 그 우선순위가
 * next dev / next build 와 같아지고, 쉘이나 CI 가 이미 넣어둔 process.env 값이
 * 파일보다 세다는 점도 같다. --dev 는 .env.development* 를, 없으면 .env.production* 을
 * 본다 (.env.local 과 .env 는 양쪽 공통).
 *
 * @returns 읽은 파일 이름들. 로그에만 쓴다.
 */
function loadEnvFiles() {
  try {
    const { loadEnvConfig } = require("@next/env");
    const quiet = { info: () => {}, error: console.error };
    return loadEnvConfig(projectDir, dev, quiet).loadedEnvFiles.map((file) => basename(file.path));
  } catch {
    // @next/env 를 못 찾아도 빌드를 세우지 않는다. 이미 들어와 있는 process.env 로만 판단한다.
    return [];
  }
}

const loaded = loadEnvFiles();
const mocking = process.env.NEXT_PUBLIC_API_MOCKING ?? "(unset)";
const how = `mocking=${mocking}${loaded.length ? `, env=${loaded.join(" ")}` : ""}`;

if (mocking === "enabled") {
  // 패키지 구조가 바뀌어도 따라가도록 exports 맵으로 찾는다.
  const source = require.resolve("msw/mockServiceWorker.js");
  mkdirSync(publicDir, { recursive: true });
  copyFileSync(source, target);
  console.log(`[msw-worker] copied → ${target} (${how})`);
} else if (existsSync(target)) {
  rmSync(target);
  console.log(`[msw-worker] removed → ${target} (${how})`);
} else {
  console.log(`[msw-worker] nothing to remove (${how})`);
}
