// Synthetic UI fixtures; no live output, approved Reference, or model-quality claim.
(function(root){
  'use strict';
  const periods=['m03_m05','m06_m08','m09_m11','m12_m02'];
  const media=['색종이, 도화지, 크레파스','블록, 종이 상자, 천','그림책, 종이, 색연필','천, 종이 띠, 작은 악기','투명한 통, 자연물 사진, 돋보기'];
  root.PLAY_PROJECT_DEMO={run_id:'ui-design-fixture-v1',periods:root.MonthlyData.seasons.map((season,p)=>({
    period_key:periods[p],rows:[...season.together.map(row=>({name:row[0],id:row[1]})),...season.free.map(row=>({name:row[1],id:row[2]}))].map((row,i)=>({
      candidate_id:`cand${i+1}`,play_name:row.name,materials:media[i%media.length],
      support_direction:'유아가 재료를 자유롭게 살펴볼 수 있는 자리를 제안합니다. 여러 표현을 비교하거나 자신의 이야기를 더하고 싶어 할 때 종이와 그림 자료를 곁에 두어, 놀이를 이어 가는 방법을 스스로 골라 볼 수 있도록 지원합니다.',
      learning_content_ids:[row.id,row.id==='nuri2019.5.1.2'?'nuri2019.2.1.2':'nuri2019.5.1.2']
    }))
  }))};
})(globalThis);
