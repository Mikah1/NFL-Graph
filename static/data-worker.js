/* All season decompression and stat aggregation runs outside the UI thread. */
const seasons=new Map(),inFlight=new Map();
let latestRequest=0;
const averages={passing_cpoe:'attempts',target_share:'targets',air_yards_share:'targets',wopr:'targets',pacr:'attempts',racr:'targets'};
async function getSeason(year,refresh,lineAvailable,advancedAvailable,trackingAvailable){
 if(!refresh&&seasons.has(year))return seasons.get(year);
 if(inFlight.has(year))return inFlight.get(year);
 const loading=(async()=>{
 const response=await fetch(`data/${year}.json.gz`,{cache:refresh?'reload':'default'});
 if(!response.ok)throw Error(`Season ${year} is unavailable (${response.status})`);
 const stream=response.body.pipeThrough(new DecompressionStream('gzip'));
 const season=JSON.parse(await new Response(stream).text());
 if(lineAvailable){try{const lines=await fetch(`data/lines-${year}.json`,{cache:refresh?'reload':'default'});if(lines.ok)season.lineSnapshot=await lines.json()}catch{}}
 if(advancedAvailable){try{const response=await fetch(`data/advanced-${year}.json.gz`,{cache:refresh?'reload':'default'});if(response.ok)season.advanced=JSON.parse(await new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).text())}catch{}}
 if(trackingAvailable){try{const response=await fetch(`data/tracking-${year}.json.gz`,{cache:refresh?'reload':'default'});if(response.ok)season.tracking=JSON.parse(await new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).text())}catch{}}
 if(seasons.size>=3)seasons.delete(seasons.keys().next().value);
 seasons.set(year,season);return season;
 })();inFlight.set(year,loading);try{return await loading}finally{inFlight.delete(year)}
}
function aggregateSeason(source,q){
 const selected=source.slices.filter(s=>s.week>=+q.weekStart&&s.week<=+q.weekEnd&&(q.seasonType==='ALL'||s.type===q.seasonType));
 const groups=new Map(),weights=new Map();
 for(const slice of selected)for(const row of slice[q.mode]){
  if(!groups.has(row.id)){groups.set(row.id,{...row,stats:{}});weights.set(row.id,{})}
  const group=groups.get(row.id),count=weights.get(row.id);
  for(const [key,value]of Object.entries(row.stats)){
   if(!Number.isFinite(value)){if(!(key in group.stats))group.stats[key]=null;continue}
   if(key==='fg_long'||key==='pt_long'){group.stats[key]=Math.max(group.stats[key]??-Infinity,value);continue}
   const weight=averages[key]?row.stats[averages[key]]||0:1;
   group.stats[key]=(group.stats[key]||0)+value*weight;count[key]=(count[key]||0)+weight;
  }
 }
 for(const [id,g]of groups){const s=g.stats;
  for(const key of Object.keys(averages))if(key in s)s[key]=weights.get(id)[key]?s[key]/weights.get(id)[key]:null;
  const ratio=(key,num,den,m=1)=>{s[key]=s[den]?m*(s[num]||0)/s[den]:null};
  if(q.mode==='players'){
   ratio('completion_pct','completions','attempts',100);ratio('yards_per_attempt','passing_yards','attempts');ratio('yards_per_carry','rushing_yards','carries');ratio('yards_per_reception','receiving_yards','receptions');ratio('catch_pct','receptions','targets',100);ratio('passing_epa_per_dropback','passing_epa','attempts');ratio('rushing_epa_per_carry','rushing_epa','carries');ratio('fg_pct','fg_made','fg_att',100);ratio('pat_pct','pat_made','pat_att',100);
  }else for(const side of ['off','def']){
   ratio(side+'_epa_per_play',side+'_epa_total',side+'_plays');ratio(side+'_success_rate',side+'_successes',side+'_plays',100);ratio(side+'_yards_per_play',side+'_yards',side+'_plays');ratio(side+'_yards_per_game',side+'_yards','games');ratio(side+'_explosive_rate',side+'_explosive_plays',side+'_plays',100);ratio(side+'_pass_rate',side+'_pass_plays',side+'_plays',100);for(const kind of ['pass','rush'])ratio(side+'_'+kind+'_epa',side+'_'+kind+'_epa_total',side+'_'+kind+'_plays');
  }
  for(const [key,value]of Object.entries(s))if(value!==null)s[key]=Math.round(value*10000)/10000;
 }
 const rows=[...groups.values()];const stats=new Set(rows.flatMap(r=>Object.keys(r.stats)));let lineSnapshot=null;
 if(source.lineSnapshot){const snapshot=source.lineSnapshot;const compatible=+q.weekStart===1&&+q.weekEnd>=snapshot.throughWeek&&q.seasonType!=='POST';const {players,teams,...metadata}=snapshot;lineSnapshot={...metadata,compatible};
  for(const row of snapshot[q.mode]){for(const key of Object.keys(row.stats))stats.add(key);if(!compatible)continue;const existing=groups.get(row.id);if(existing)Object.assign(existing.stats,row.stats);else rows.push({...row,stats:{...row.stats}})}
 }
 let advancedCoverage=null;if(source.advanced)advancedCoverage=mergeAdvanced(rows,stats,source.advanced,q);
 let trackingCoverage=null;if(source.tracking)trackingCoverage=mergeAdvanced(rows,stats,source.tracking,q);
 return {rows,stats:[...stats].sort(),lineSnapshot,advancedCoverage,trackingCoverage,season:source.season,weeks:[...new Set(source.slices.map(s=>s.week))].sort((a,b)=>a-b),plays:selected.reduce((n,s)=>n+s.plays,0),updated:source.updated,stale:Date.now()/1000-source.updated>21600,sources:[...source.sources,...(source.lineSnapshot?[source.lineSnapshot.source]:[]),...(source.advanced?[source.advanced.source]:[]),...(source.tracking?[source.tracking.source]:[])]};
}
function passerRating(attempts,completions,yards,touchdowns,interceptions){if(!attempts)return null;return [(completions/attempts-.3)*5,(yards/attempts-3)*.25,touchdowns/attempts*20,2.375-interceptions/attempts*25].reduce((n,p)=>n+Math.max(0,Math.min(2.375,p)),0)/6*100}
function mergeAdvanced(rows,keys,data,q){
 const selected=data.slices.filter(s=>s.week>=+q.weekStart&&s.week<=+q.weekEnd&&(q.seasonType==='ALL'||s.type===q.seasonType)),groups=new Map();
 for(const slice of data.slices)for(const row of slice[q.mode])for(const key of Object.keys(row.stats))keys.add(key);
 for(const slice of selected)for(const row of slice[q.mode]){
  if(!groups.has(row.id))groups.set(row.id,{...row,stats:{},counts:{},chartedGames:0});const g=groups.get(row.id);g.chartedGames+=row.chartedGames;
  for(const [key,value]of Object.entries(row.stats))if(!(key in data.ratios)&&!['def_passer_rating_allowed','receiving_passer_rating_when_targeted','ngs_passing_air_yards_differential'].includes(key)&&Number.isFinite(value))g.stats[key]=(data.maxStats||[]).includes(key)?Math.max(g.stats[key]??-Infinity,value):(g.stats[key]||0)+value;
  for(const [key,value]of Object.entries(row.counts))g.counts[key]=(g.counts[key]||0)+value;
 }
 const index=new Map(rows.map(r=>[r.id,r]));
 for(const g of groups.values()){
  const s=g.stats,c=g.counts,value=k=>k.startsWith('@')?c[k.slice(1)]:s[k];
  for(const [key,[num,den,scale]]of Object.entries(data.ratios))if(value(num)!==undefined)s[key]=value(den)?value(num)/value(den)*scale:null;
  if(['def_targets','def_completions_allowed','def_yards_allowed','def_receiving_tds_allowed'].every(k=>k in s)&&'def_interceptions' in c)s.def_passer_rating_allowed=passerRating(s.def_targets,s.def_completions_allowed,s.def_yards_allowed,s.def_receiving_tds_allowed,c.def_interceptions);
  if(['rec_targets','rec_catches','rec_yards','rec_tds'].every(k=>k in c)&&'receiving_interceptions_on_targets' in s)s.receiving_passer_rating_when_targeted=passerRating(c.rec_targets,c.rec_catches,c.rec_yards,c.rec_tds,s.receiving_interceptions_on_targets);
  if('ngs_passing_completed_air_yards' in s&&'ngs_passing_intended_air_yards' in s)s.ngs_passing_air_yards_differential=s.ngs_passing_completed_air_yards-s.ngs_passing_intended_air_yards;
  for(const key of Object.keys(s))if(s[key]!==null)s[key]=Math.round(s[key]*10000)/10000;
  let row=index.get(g.id);if(!row){const {counts,chartedGames,...extra}=g;row={...extra,stats:{games:chartedGames}};rows.push(row)}
  for(const [key,value]of Object.entries(s))if(!(key in row.stats))row.stats[key]=value;row.advancedSamples={...(row.advancedSamples||{}),...c};
 }
 return {updated:data.updated,categories:data.coverage,selectedWeeks:[...new Set(selected.map(s=>s.week))].sort((a,b)=>a-b),source:data.source};
}
self.onmessage=async event=>{const {id,query}=event.data;latestRequest=id;try{const source=await getSeason(+query.season,query.refresh==='1',query.lineAvailable,query.advancedAvailable,query.trackingAvailable);if(id!==latestRequest)return;self.postMessage({id,result:aggregateSeason(source,query)})}catch(error){self.postMessage({id,error:error.message})}};
