(function(root){
  'use strict';
  const Model=root.PlayEditorModel||(typeof require==='function'?require('./yearly/model.js'):null);
  function periodKey(month){if(!Number.isInteger(month)||month<1||month>12)throw Error('INVALID_MONTH');return month>=3&&month<=5?'m03_m05':month>=6&&month<=8?'m06_m08':month>=9&&month<=11?'m09_m11':'m12_m02';}
  function read(data,curriculum,saved,month){
    const key=periodKey(month);
    if(!saved)return {status:'missing',period:key,count:0,plays:[]};
    try{
    const model=new Model(data,curriculum);
    if(!model.restore(saved))return {status:'invalid',period:key,count:0,plays:[]};
    const selected=model.state.selected[key];
    if(selected.length!==5)return {status:'incomplete',period:key,count:selected.length,plays:[]};
    const placed=model.state.slots[key].filter(Boolean),order=[...placed,...selected.filter(id=>!placed.includes(id))];
    return {status:'ready',period:key,count:5,source:data.run_id,plays:order.map(id=>{const r=model.row(key,id);return {id,name:r.play_name,materials:r.materials,support:r.support_direction,contentIds:[...r.learning_content_ids]};})};
    }catch{return {status:'invalid',period:key,count:0,plays:[]};}
  }
  root.MonthlyParentBridge={read,periodKey};
  if(typeof module!=='undefined')module.exports=root.MonthlyParentBridge;
})(globalThis);
