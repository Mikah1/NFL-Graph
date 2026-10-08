const fs=require('node:fs'),vm=require('node:vm'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const context=vm.createContext({self:{}});
vm.runInContext(fs.readFileSync('static/data-worker.js','utf8'),context);
context.source=JSON.parse(zlib.gunzipSync(fs.readFileSync(process.argv[2])));
if(process.argv[4])context.source.lineSnapshot=JSON.parse(fs.readFileSync(process.argv[4]));
if(process.argv[5])context.source.advanced=JSON.parse(zlib.gunzipSync(fs.readFileSync(process.argv[5])));
if(process.argv[9])context.source.tracking=JSON.parse(zlib.gunzipSync(fs.readFileSync(process.argv[9])));
const expected=JSON.parse(fs.readFileSync(process.argv[3]));
for(const mode of ['teams','players']){
 context.query={mode,weekStart:+(process.argv[6]||1),weekEnd:+(process.argv[7]||18),seasonType:process.argv[8]||'REG'};
 const actual=vm.runInContext('aggregateSeason(source,query)',context);
 assert.equal(actual.rows.length,expected[mode].rows.length);
 assert.equal(actual.plays,expected[mode].plays);
 const rows=new Map(actual.rows.map(row=>[row.id,row]));
 for(const row of expected[mode].rows){
  const counterpart=rows.get(row.id);assert.ok(counterpart);
  if(row.advancedSamples)for(const [k,v] of Object.entries(row.advancedSamples))assert.ok(Math.abs(v-counterpart.advancedSamples[k])<0.003);
  for(const[key,value]of Object.entries(row.stats)){
   const other=counterpart.stats[key];
   if(value===null){assert.equal(other,null,`${row.id} ${key}`);continue}
   assert.ok(Math.abs(value-other)<=0.003,`${mode} ${row.id} ${key}: ${value} != ${other}`);
  }
 }
}
console.log('Published worker statistics match Python calculations within snapshot rounding tolerance.');

if(context.source.lineSnapshot){context.query={mode:'players',weekStart:2,weekEnd:3,seasonType:'REG'};const filtered=vm.runInContext('aggregateSeason(source,query)',context);assert.equal(filtered.lineSnapshot.compatible,false);assert.ok(filtered.rows.every(r=>!Object.keys(r.stats).some(k=>k.startsWith('line_'))));}
