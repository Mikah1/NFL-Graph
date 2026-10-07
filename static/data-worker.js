/* All season decompression and stat aggregation runs outside the UI thread. */
const seasons=new Map();
const averages={passing_cpoe:'attempts',target_share:'targets',air_yards_share:'targets',wopr:'targets',pacr:'attempts',racr:'targets'};
async function getSeason(year,refresh){
 if(!refresh&&seasons.has(year))return seasons.get(year);
 const response=await fetch(`data/${year}.json.gz`,{cache:refresh?'reload':'default'});
 if(!response.ok)throw Error(`Season ${year} is unavailable (${response.status})`);
 const stream=response.body.pipeThrough(new DecompressionStream('gzip'));
 const season=JSON.parse(await new Response(stream).text());
 if(seasons.size>=3)seasons.delete(seasons.keys().next().value);
 seasons.set(year,season);return season;
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
 const rows=[...groups.values()];return {rows,stats:[...new Set(rows.flatMap(r=>Object.keys(r.stats)))].sort(),season:source.season,weeks:[...new Set(source.slices.map(s=>s.week))].sort((a,b)=>a-b),plays:selected.reduce((n,s)=>n+s.plays,0),updated:source.updated,stale:Date.now()/1000-source.updated>21600,sources:source.sources};
}
self.onmessage=async event=>{const {id,query}=event.data;try{const source=await getSeason(+query.season,query.refresh==='1');self.postMessage({id,result:aggregateSeason(source,query)})}catch(error){self.postMessage({id,error:error.message})}};
