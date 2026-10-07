"""Fieldvision: dependency-free NFL analytics server and disk-backed data importer."""
import csv, gzip, io, json, math, os, time, threading, urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / 'cache'
CACHE.mkdir(exist_ok=True)
CURRENT = time.localtime().tm_year - (time.localtime().tm_mon < 3)
BASE = 'https://github.com/nflverse/nflverse-data/releases/download'
locks = defaultdict(threading.Lock)
memory = {}
aggregate_cache = {}
refresh_jobs = set()
ALIASES = {'LA':'LAR', 'OAK':'LV', 'SD':'LAC', 'STL':'LAR', 'WSH':'WAS'}
AFC = set('BAL BUF CIN CLE DEN HOU IND JAX KC LAC LV MIA NE NYJ PIT TEN'.split())

def number(v):
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError): return None

def fetch(name, url, refresh=False):
    path = CACHE / name
    with locks[name]:
        fresh = path.exists() and time.time() - path.stat().st_mtime < 21600
        if not refresh and path.exists():
            if not fresh and name not in refresh_jobs:
                refresh_jobs.add(name)
                def update():
                    try: fetch(name,url,True)
                    except Exception: pass
                    finally: refresh_jobs.discard(name)
                threading.Thread(target=update,daemon=True).start()
            return path
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'Fieldvision/1.0'})
            with urllib.request.urlopen(req, timeout=90) as res:
                content = res.read()
            temp = path.with_suffix(path.suffix + '.tmp')
            temp.write_bytes(content)
            temp.replace(path)
        except Exception:
            if not path.exists(): raise
        return path

def metadata(refresh=False):
    p = fetch('teams.json','https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams',refresh)
    entries = json.loads(p.read_text())['sports'][0]['leagues'][0]['teams']
    return {ALIASES.get(t['team']['abbreviation'],t['team']['abbreviation']):t['team'] for t in entries}

def team_info(abbr, teams):
    a = ALIASES.get(abbr,abbr)
    t = teams.get(a,{})
    return {'team':a,'name':t.get('displayName',a),'short':a,'logo':(t.get('logos') or [{}])[0].get('href',''),'color':'#'+t.get('color','325948'),'conference':'AFC' if a in AFC else 'NFC'}

def load(season, refresh=False):
    key = str(season)
    with locks['season'+key]:
        if not refresh and key in memory and time.time()-memory[key]['loaded'] < 21600 and all((CACHE / name).stat().st_mtime <= memory[key]['loaded'] for name in ('teams.json',f'players_{season}.csv',f'pbp_{season}.csv.gz')): return memory[key]
        with ThreadPoolExecutor(max_workers=3) as pool:
            tp=pool.submit(metadata, refresh)
            pp=pool.submit(fetch,f'players_{season}.csv',f'{BASE}/stats_player/stats_player_week_{season}.csv',refresh)
            bp=pool.submit(fetch,f'pbp_{season}.csv.gz',f'{BASE}/pbp/play_by_play_{season}.csv.gz',refresh)
            teams=tp.result(); player_path=pp.result(); pbp_path=bp.result()
        with player_path.open() as f:
            players=list(csv.DictReader(f))
        with gzip.open(pbp_path,'rt') as f:
            # Retain only required columns, so multiple seasons stay reasonably small.
            fields='game_id week season_type posteam defteam play_type qb_dropback rush_attempt pass_attempt epa yards_gained success touchdown interception fumble_lost down yardline_100'.split()
            plays=[{k:r.get(k,'') for k in fields} for r in csv.DictReader(f)]
        data={'teams':teams,'players':players,'plays':plays,'loaded':time.time(),'updated':max(player_path.stat().st_mtime,pbp_path.stat().st_mtime),'stale':time.time()-min(player_path.stat().st_mtime,pbp_path.stat().st_mtime)>21600}
        if key not in memory and len(memory)>=3:
            oldest=min(memory,key=lambda k:memory[k]['loaded'])
            memory.pop(oldest)
        memory[key]=data
        return data

def aggregate(q):
    # Coalesce requests for the same slice, including team/player switches.
    key=tuple(q.get(k,[default])[0] for k,default in [('season',str(CURRENT)),('weekStart','1'),('weekEnd','22'),('seasonType','REG')])
    with locks['aggregate'+repr(key)]: return _aggregate(q)

def _aggregate(q):
    season=int(q.get('season',[CURRENT])[0])
    if not 1999<=season<=CURRENT: raise ValueError('Choose a season from 1999 through the current season.')
    data=load(season,q.get('refresh',['0'])[0]=='1')
    low=int(q.get('weekStart',['1'])[0]); high=int(q.get('weekEnd',['22'])[0])
    typ=q.get('seasonType',['REG'])[0]
    cache_key=(season,low,high,typ,data['loaded'])
    if cache_key in aggregate_cache: return aggregate_cache[cache_key][q.get('mode',['teams'])[0]]
    def included(r): return low<=int(r.get('week') or 0)<=high and (typ=='ALL' or r.get('season_type')==typ)
    player_rows=[r for r in data['players'] if included(r)]
    groups={}; counts=defaultdict(lambda:defaultdict(int))
    averages={'passing_cpoe':'attempts','target_share':'targets','air_yards_share':'targets','wopr':'targets','pacr':'attempts','racr':'targets'}
    ignore=set('player_id player_name player_display_name position position_group headshot_url season week season_type game_id team recent_team opponent_team'.split())
    for r in player_rows:
        pid=r['player_id']
        if pid not in groups:
            info=team_info(r.get('team',r.get('recent_team','')),data['teams'])
            groups[pid]={**info,'id':pid,'name':r.get('player_display_name') or r.get('player_name'),'short':r.get('player_name'),'position':r['position'],'logo':r.get('headshot_url',''),'stats':{},'_games':set()}
        g=groups[pid]; g['_games'].add(r['game_id'])
        for k,v in r.items():
            if k in ignore or k.endswith('_list'): continue
            n=number(v)
            if n is None: continue
            weight=number(r.get(averages[k])) or 0 if k in averages else 1
            if k in ('fg_long','pt_long'): g['stats'][k]=max(g['stats'].get(k,0),n)
            elif k not in ('fg_pct','pat_pct'): g['stats'][k]=g['stats'].get(k,0)+n*weight
            counts[pid][k]+=weight
    for pid,g in groups.items():
        s=g['stats']; s['games']=len(g.pop('_games'))
        for k in averages:
            if k in s: s[k]=s[k]/counts[pid][k] if counts[pid][k] else None
        def ratio(name,n,d,m=1): s[name]=s.get(n,0)/s[d]*m if s.get(d) else None
        ratio('completion_pct','completions','attempts',100); ratio('yards_per_attempt','passing_yards','attempts')
        ratio('yards_per_carry','rushing_yards','carries'); ratio('yards_per_reception','receiving_yards','receptions')
        ratio('catch_pct','receptions','targets',100); ratio('passing_epa_per_dropback','passing_epa','attempts')
        ratio('rushing_epa_per_carry','rushing_epa','carries'); ratio('fg_pct','fg_made','fg_att',100); ratio('pat_pct','pat_made','pat_att',100)
        s['total_yards']=s.get('passing_yards',0)+s.get('rushing_yards',0)+s.get('receiving_yards',0)
        s['touchdowns']=s.get('passing_tds',0)+s.get('rushing_tds',0)+s.get('receiving_tds',0)
    ts={}; selected=[r for r in data['plays'] if included(r)]; valid=0
    for r in selected:
        if r['play_type'] not in ('pass','run') or r.get('epa')=='' or not r['posteam']: continue
        e=number(r['epa']); y=number(r['yards_gained'])
        if e is None or y is None: continue
        valid+=1
        for side,abbr in [('off',r['posteam']),('def',r['defteam'])]:
            if not abbr: continue
            a=ALIASES.get(abbr,abbr)
            if a not in ts: ts[a]={**team_info(a,data['teams']),'id':a,'position':'TEAM','stats':defaultdict(float),'_games':set()}
            g=ts[a]; s=g['stats']; g['_games'].add(r['game_id'])
            s[side+'_plays']+=1; s[side+'_epa_total']+=e; s[side+'_yards']+=y
            s[side+'_successes']+=e>0
            if r['play_type']=='pass': s[side+'_pass_plays']+=1; s[side+'_pass_epa_total']+=e; s[side+'_pass_yards']+=y
            else: s[side+'_rush_plays']+=1; s[side+'_rush_epa_total']+=e; s[side+'_rush_yards']+=y
            s[side+'_touchdowns']+=number(r.get('touchdown')) or 0
            s[side+'_turnovers']+=(number(r.get('interception')) or 0)+(number(r.get('fumble_lost')) or 0)
            s[side+'_explosive_plays']+=y>=20
    for g in ts.values():
        s=g['stats']; s['games']=len(g.pop('_games'))
        for side in ('off','def'):
            n=s[side+'_plays']
            s[side+'_epa_per_play']=s[side+'_epa_total']/n if n else None
            s[side+'_success_rate']=100*s[side+'_successes']/n if n else None
            s[side+'_yards_per_play']=s[side+'_yards']/n if n else None
            s[side+'_yards_per_game']=s[side+'_yards']/s['games']
            s[side+'_explosive_rate']=100*s[side+'_explosive_plays']/n if n else None
            for kind in ('pass','rush'):
                den=s[side+'_'+kind+'_plays']
                s[side+'_'+kind+'_epa']=s[side+'_'+kind+'_epa_total']/den if den else None
            s[side+'_pass_rate']=100*s[side+'_pass_plays']/n if n else None
    result={}
    for mode,rows in [('teams',list(ts.values())),('players',list(groups.values()))]:
        for g in rows: g['stats']={k:round(v,4) if v is not None else None for k,v in g['stats'].items()}
        stat_keys=sorted({k for g in rows for k in g['stats']})
        result[mode]={'rows':rows,'stats':stat_keys,'season':season,'weeks':sorted({int(r['week']) for r in data['players']}),'plays':valid,'updated':data['updated'],'stale':data['stale'],'sources':[{'name':'nflverse','url':'https://github.com/nflverse/nflverse-data'},{'name':'ESPN','url':'https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams'}]}
    if len(aggregate_cache)>=24: aggregate_cache.pop(next(iter(aggregate_cache)))
    aggregate_cache[cache_key]=result
    return result[q.get('mode',['teams'])[0]]

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT/'static'),**kwargs)
    def do_GET(self):
        p=urlparse(self.path)
        if p.path=='/api/config': return self.send_json({'currentSeason':CURRENT,'seasons':list(range(CURRENT,1998,-1))})
        if p.path=='/api/data':
            try: self.send_json(aggregate(parse_qs(p.query)))
            except Exception as e: self.send_json({'error':f'This season could not be loaded: {e}. Try another season or retry the import.'},502)
            return
        super().do_GET()
    def send_json(self,obj,status=200):
        raw=json.dumps(obj,allow_nan=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)

if __name__=='__main__':
    port=int(os.environ.get('PORT','3000'))
    print(f'Fieldvision preview: http://localhost:{port}',flush=True)
    ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
