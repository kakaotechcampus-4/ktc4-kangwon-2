import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
registerHooks({resolve(s,c,n){
  if (["../onboarding/types","./demo-session","./account-store","../auth/demo-session","./types","../onboarding/settings"].includes(s)) return n(`${s}.ts`,c);
  return n(s,c);
}});
const auth = await import("../lib/auth/local-account.ts");
const session = await import("../lib/auth/demo-session.ts");
const settings = await import("../lib/onboarding/settings.ts");
const { EMPTY_CLASS_SETTINGS } = await import("../lib/onboarding/types.ts");
function setup() {
  const values = new Map(), tab = new Map();
  const storage = map => ({getItem:key=>map.get(key)??null,setItem:(key,value)=>map.set(key,value),removeItem:key=>map.delete(key)});
  globalThis.localStorage = storage(values);
  globalThis.window = Object.assign(new EventTarget(), {localStorage,sessionStorage:storage(tab)});
  return {values,tab};
}
async function login(email) {
  await auth.verifyAccount(email,"test-password-123");
  assert.equal(session.startDemoSession(),true);
}

test("common guard handles unauthenticated access, unfinished onboarding and returning login", async () => {
  setup();
  assert.equal(auth.accessRedirect(),"/login");
  await auth.registerAccount("노덕철","first@example.com","test-password-123");
  await login("first@example.com");
  // /home와 다른 서비스 화면은 동일한 공통 guard를 사용한다.
  assert.equal(auth.accessRedirect(true),"/onboarding/center");
  assert.equal(auth.accessRedirect(false),null);
  assert.equal(auth.accessRedirect(true),"/onboarding/center"); // 새로고침에서도 동일
  assert.equal(settings.saveClassSettings({...EMPTY_CLASS_SETTINGS,directorName:"원장",regionProvince:"세종특별자치시",regionDistrict:"세종특별자치시",classes:[{...EMPTY_CLASS_SETTINGS.classes[0],className:"반",teacherName:"담임",ageGroup:"3"}],orgName:"새싹어린이집",completedAt:new Date().toISOString()}),true);
  assert.equal(auth.completeAccountOnboarding(),true);
  assert.equal(auth.accessRedirect(true),null);
  assert.equal(session.endDemoSession(),true);
  assert.equal(auth.accessRedirect(),"/login");
  assert.equal(settings.loadClassSettings(),null);
  assert.equal(settings.saveClassSettings(EMPTY_CLASS_SETTINGS),false);
  await login("first@example.com");
  assert.equal(auth.loginDestination(),"/");
  assert.equal(auth.accessRedirect(true),null);
});

test("corrupt legacy JSON and malformed legacy objects do not block valid login or signup", async () => {
  const {values}=setup();
  await auth.registerAccount("첫째","first@example.com","test-password-123");
  for (const raw of ["{", "null", "[]", '{"email":42}', '{"email":"old@example.com","salt":null}']) {
    values.set("saessak.demoAccount",raw);
    await login("first@example.com");
    assert.equal(auth.accountName(),"첫째");
    session.endDemoSession();
  }
  values.set("saessak.demoAccount","{");
  await auth.registerAccount("둘째","second@example.com","test-password-123");
  await login("second@example.com");
  assert.equal(auth.accountName(),"둘째");
});

test("organization, teacher and onboarding status stay isolated after account switch", async () => {
  setup();
  await auth.registerAccount("노덕철","first@example.com","test-password-123");
  await auth.registerAccount("이서연","second@example.com","test-password-123");
  await login("first@example.com");
  settings.saveClassSettings({...EMPTY_CLASS_SETTINGS,directorName:"원장",regionProvince:"세종특별자치시",regionDistrict:"세종특별자치시",classes:[{...EMPTY_CLASS_SETTINGS.classes[0],className:"반",teacherName:"담임",ageGroup:"3"}],orgName:"새싹어린이집"});
  auth.completeAccountOnboarding();
  assert.equal(settings.planHeaderFor(settings.loadClassSettings(),auth.accountName()),"새싹어린이집 · 노덕철 선생님 · 반");
  session.endDemoSession();
  await login("second@example.com");
  assert.equal(settings.loadClassSettings(),null);
  assert.equal(auth.accessRedirect(),"/onboarding/center");
  settings.saveClassSettings({...EMPTY_CLASS_SETTINGS,directorName:"원장",regionProvince:"세종특별자치시",regionDistrict:"세종특별자치시",classes:[{...EMPTY_CLASS_SETTINGS.classes[0],className:"반",teacherName:"담임",ageGroup:"3"}],orgName:"푸른어린이집"});
  assert.equal(settings.planHeaderFor(settings.loadClassSettings(),auth.accountName()),"푸른어린이집 · 이서연 선생님 · 반");
  session.endDemoSession();
  await login("first@example.com");
  assert.equal(settings.planHeaderFor(settings.loadClassSettings(),auth.accountName()),"새싹어린이집 · 노덕철 선생님 · 반");
  assert.equal(auth.accessRedirect(),null);
});

test("legacy accounts missing display names do not substitute classroom teachers for account names", async () => {
  const {values}=setup();
  await auth.registerAccount("기존 이름","first@example.com","test-password-123");
  const key="saessak.demoAccount:first%40example.com";
  const account=JSON.parse(values.get(key));delete account.name;values.set(key,JSON.stringify(account));
  await login("first@example.com");
  const saved={...EMPTY_CLASS_SETTINGS,directorName:"원장",regionProvince:"세종특별자치시",regionDistrict:"세종특별자치시",classes:[{...EMPTY_CLASS_SETTINGS.classes[0],className:"반",teacherName:"담임",ageGroup:"3"}],orgName:"새싹어린이집",classes:[{...EMPTY_CLASS_SETTINGS.classes[0],teacherName:"노덕철"}]};
  settings.saveClassSettings(saved);
  assert.equal(settings.planHeaderFor(settings.loadClassSettings(),auth.accountName()),"새싹어린이집 · 선생님");
  assert.equal(settings.planHeaderFor(null,null),"기관 미설정 · 선생님");
});

test("PRD onboarding URLs, primary class migration, removal and account roles", async()=>{
 setup();await auth.registerAccount("김수린","primary@example.com","test-password-123");await login("primary@example.com");
 assert.equal(auth.onboardingDestination(),"/onboarding/center");
 const center={...EMPTY_CLASS_SETTINGS,orgName:"기관",directorName:"원장",regionProvince:"세종특별자치시",regionDistrict:"세종특별자치시"};
 settings.saveClassSettings(center);assert.equal(auth.onboardingDestination(),"/onboarding/classes");
 const classes=[{...EMPTY_CLASS_SETTINGS.classes[0],id:"a",className:"국화반",teacherName:"김국화",ageGroup:"3"},{...EMPTY_CLASS_SETTINGS.classes[0],id:"b",className:"난초반",teacherName:"김난초",ageGroup:"4"}];
 settings.saveClassSettings({...center,classes});assert.equal(settings.primaryClassFor(settings.loadClassSettings()).id,"a");
 assert.equal(auth.onboardingDestination(),"/onboarding/children");
 settings.saveClassSettings({...center,classes,primaryClassId:"b"});assert.equal(settings.primaryClassFor(settings.loadClassSettings()).className,"난초반");
 assert.equal(settings.planHeaderFor(settings.loadClassSettings(),auth.accountName()),"기관 · 김수린 선생님 · 난초반");
 assert.equal(auth.completeAccountOnboarding(),true);assert.equal(auth.loginDestination(),"/");
 settings.saveClassSettings({...center,classes:[classes[0]],primaryClassId:"b"});assert.equal(settings.primaryClassFor(settings.loadClassSettings()).id,"a");
});
