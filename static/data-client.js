// Static data transport for GitHub Pages. Python preview APIs remain supported.
let staticHosting=false;
let worker,lineSeasons=[],advancedSeasons=[],trackingSeasons=[];
const pending=new Map();let sequence=0;
async function loadConfiguration(){
 let response=await fetch('data/config.json');
 staticHosting=response.ok;
 if(!staticHosting)response=await fetch('/api/config');
 if(!response.ok)throw Error('Site data configuration could not be loaded');const result=await response.json();lineSeasons=result.lineSeasons||[];advancedSeasons=result.advancedSeasons||[];trackingSeasons=result.trackingSeasons||[];return result;
}
async function loadStatistics(query,signal){
 if(!staticHosting){const response=await fetch('/api/data?'+query,{signal});const result=await response.json();if(!response.ok)throw Error(result.error||'Data could not be imported');return result}
 if(!worker){worker=new Worker(new URL('data-worker.js',location.href));worker.onmessage=event=>{const request=pending.get(event.data.id);if(!request)return;pending.delete(event.data.id);request.cleanup();event.data.error?request.reject(Error(event.data.error)):request.resolve(event.data.result)};worker.onerror=()=>{for(const request of pending.values()){request.cleanup();request.reject(Error('The data worker could not load. Reload the page to retry.'))}pending.clear();worker.terminate();worker=null}}
 return new Promise((resolve,reject)=>{const id=++sequence;const abort=()=>{pending.delete(id);reject(new DOMException('Request superseded','AbortError'))};if(signal?.aborted)return abort();signal?.addEventListener('abort',abort,{once:true});pending.set(id,{resolve,reject,cleanup:()=>signal?.removeEventListener('abort',abort)});worker.postMessage({id,query:{...Object.fromEntries(query),lineAvailable:lineSeasons.includes(+query.get('season')),advancedAvailable:advancedSeasons.includes(+query.get('season')),trackingAvailable:trackingSeasons.includes(+query.get('season'))}})});
}
