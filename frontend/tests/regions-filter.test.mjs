/**
 * 지역 고르개 검색칸: 이름이나 초성(ㄱ~ㅎ)으로 목록을 거른다.
 * 화면이 아니라 거르는 순수 함수(`matchesRegion`)만 본다.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

const { matchesRegion, districtsFor } = await import("../lib/onboarding/regions.ts");

test("빈 검색어와 공백만 든 검색어는 다 맞는다", () => {
  assert.equal(matchesRegion("춘천시", ""), true);
  assert.equal(matchesRegion("춘천시", "   "), true);
});

test("초성만 쳐도 앞에서부터 맞는다", () => {
  assert.equal(matchesRegion("춘천시", "ㅊㅊ"), true);
  assert.equal(matchesRegion("충청북도", "ㅊㅊ"), true);
  assert.equal(matchesRegion("청주시", "ㅊㅊ"), false); // 청주시는 ㅊㅈㅅ
  assert.equal(matchesRegion("춘천시", "ㅎㅎ"), false);
});

test("글자와 초성을 섞어 쳐도 된다", () => {
  assert.equal(matchesRegion("춘천시", "춘ㅊ"), true);
  assert.equal(matchesRegion("춘천시", "춘천ㅅ"), true);
  assert.equal(matchesRegion("춘천시", "춘ㅈ"), false);
});

test("이름 글자를 그대로 쳐도 앞에서부터 맞는다", () => {
  assert.equal(matchesRegion("강릉시", "강"), true);
  assert.equal(matchesRegion("강원특별자치도", "강원"), true);
  assert.equal(matchesRegion("서울특별시", "ㅅㅇ"), true);
  assert.equal(matchesRegion("강원특별자치도", "특별"), false); // 이름 가운데서는 찾지 않는다
  assert.equal(matchesRegion("서울특별시", "ㅂㅅ"), false);
  assert.equal(matchesRegion("강릉시", "속"), false);
});

test("검색어가 이름보다 길면 안 맞는다", () => {
  assert.equal(matchesRegion("중구", "ㅈㄱㅅ"), false);
});

test("강원 시·군 중 ㅊ 로 시작하는 곳은 춘천시와 철원군뿐이다(삼척시 · 평창군은 아니다)", () => {
  const hit = districtsFor("강원특별자치도").filter((d) => matchesRegion(d, "ㅊ"));
  assert.deepEqual(hit.sort(), ["철원군", "춘천시"]);
});
