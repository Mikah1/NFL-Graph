"""Import ESPN's published cumulative line-play leaderboard tables.

Rates are source snapshots, never summed across weeks or used for weekly splits.
"""
import csv, json, re, time
from datetime import datetime
from html import unescape
from html.parser import HTMLParser

ARTICLES={2026:49742016,2025:46138675,2024:41040723,2023:38356170}
RATE_KEYS={'PBWR':'line_pass_block_win_rate','RBWR':'line_run_block_win_rate','PRWR':'line_pass_rush_win_rate','RSWR':'line_run_stop_win_rate'}
LINE_PREFIXES=('line_pass_block_','line_run_block_','line_pass_rush_','line_run_stop_')

class Text(HTMLParser):
    def __init__(self): super().__init__();self.parts=[]
    def handle_data(self,text): self.parts.append(text)
def clean(value):
    p=Text();p.feed(str(value));return unescape(''.join(p.parts)).strip()
def numeric(value):
    match=re.match(r'^\s*(-?\d+(?:\.\d+)?)',clean(value))
    return float(match.group(1)) if match else None

def parse_article(article,season,rosters,team_info):
    if str(season) not in article.get('headline',''): raise ValueError('ESPN article does not match selected season')
    story=clean(article.get('story',''))
    match=re.search(r'Through\s+Week\s+(\d+)',story,re.I)
    # Older annual articles provide final regular-season leaderboards.
    through=int(match.group(1)) if match else (18 if season>=2021 else 17)
    updated=article.get('lastModified') or article.get('published')
    timestamp=datetime.fromisoformat(updated.replace('Z','+00:00')).timestamp() if updated else time.time()
    link=article.get('links',{}).get('web',{}).get('href',f'https://www.espn.com/nfl/story/_/id/{ARTICLES[season]}')
    identities={str(r['espn_id']).split('.')[0]:r for r in rosters if r.get('espn_id')}
    players={};teams={};tables=0
    for module in article.get('inlines',[]):
        table=module.get('json',{})
        if not isinstance(table,dict) or not table.get('header') or not table.get('body'): continue
        headers=[clean(h) for h in table['header']];title=module.get('headline','')
        if not any(h in RATE_KEYS for h in headers): continue
        tables+=1
        for cells in table['body']:
            if len(cells)!=len(headers): raise ValueError('ESPN table schema changed')
            values=dict(zip(headers,cells))
            if any(h.lower()=='team' for h in headers) and 'Name' not in headers:
                cell=values[next(h for h in headers if h.lower()=='team')]
                match_team=re.search(r'/name/([a-z0-9]+)/',cell,re.I)
                if not match_team: raise ValueError('ESPN team identifier missing')
                info=team_info(match_team.group(1).upper())
                row=teams.setdefault(info['team'],{**info,'id':info['team'],'position':'TEAM','stats':{}})
                for h,key in RATE_KEYS.items():
                    if h in values:
                        value=numeric(values[h])
                        if value is None or not 0<=value<=100: raise ValueError('Invalid ESPN win rate')
                        row['stats'][key]=value
                        rank=re.search(r'\((\d+)\)',clean(values[h]))
                        if rank: row['stats'][key.replace('win_rate','rank')]=int(rank.group(1))
                continue
            match_player=re.search(r'/id/(\d+)/',values.get('Name',''))
            if not match_player: raise ValueError('ESPN player identifier missing')
            espn=match_player.group(1);roster=identities.get(espn,{})
            name=clean(values['Name']).replace("\\'", "'")
            info=team_info(clean(values['Team']))
            position=roster.get('position') or ('OT' if title.startswith('OT') else 'IOL' if title.startswith('IOL') else 'DT' if title.startswith('DT') else 'EDGE')
            pid=roster.get('gsis_id') or 'espn:'+espn
            row=players.setdefault(pid,{**info,'id':pid,'espnId':espn,'name':name,'short':name.split()[0][0]+'.'+' '.join(name.split()[1:]),'position':position,'logo':f'https://a.espncdn.com/i/headshots/nfl/players/full/{espn}.png?w=80&h=80','stats':{}})
            for h,key in RATE_KEYS.items():
                if h not in values: continue
                rate=numeric(values[h]);wins=numeric(values.get('Wins',''));plays=numeric(values.get('Plays',''))
                if rate is None or not 0<=rate<=100 or plays is not None and (plays<0 or wins is not None and not 0<=wins<=plays): raise ValueError('Invalid ESPN line-play counts/rate')
                row['stats'][key]=rate
                for suffix,column in [('wins','Wins'),('plays','Plays'),('rank','Rank'),('double_team_rate','DT%')]:
                    value=numeric(values.get(column,''))
                    if value is not None: row['stats'][key.replace('win_rate',suffix)]=value
    if tables<8 or len(teams)!=32 or len(players)<50: raise ValueError('Incomplete ESPN line-play leaderboards')
    return {'season':season,'throughWeek':through,'updated':timestamp,'coverage':'Published qualifying leaders only; position-group rankings. Cumulative regular-season snapshot.', 'source':{'name':'ESPN Analytics / NFL Next Gen Stats','url':link},'players':list(players.values()),'teams':list(teams.values())}

def load_line_stats(season,refresh=False):
    import server
    if season not in ARTICLES: return None
    cache=server.CACHE/f'line_stats_{season}.json'
    if cache.exists() and not refresh and time.time()-cache.stat().st_mtime<21600: return json.loads(cache.read_text())
    try:
        path=server.fetch(f'line_article_{season}.json',f'https://cdn.espn.com/core/nfl/story/_/id/{ARTICLES[season]}?xhr=1',refresh)
        article=json.loads(path.read_text())['content']
        roster_path=server.fetch(f'roster_{season}.csv',f'{server.BASE}/rosters/roster_{season}.csv',refresh)
        with roster_path.open() as f: roster=list(csv.DictReader(f))
        teams=server.metadata()
        result=parse_article(article,season,roster,lambda abbr:server.team_info(abbr,teams))
        temp=cache.with_suffix('.tmp');temp.write_text(json.dumps(result));temp.replace(cache)
        return result
    except Exception:
        if cache.exists(): return json.loads(cache.read_text())
        raise

def merge_snapshot(result,snapshot,query):
    if not snapshot: return result
    low=int(query.get('weekStart',['1'])[0]);high=int(query.get('weekEnd',['22'])[0]);typ=query.get('seasonType',['REG'])[0]
    compatible=low==1 and high>=snapshot['throughWeek'] and typ in ('REG','ALL')
    result={**result,'rows':[{**r,'stats':dict(r['stats'])} for r in result['rows']],'lineSnapshot':{k:v for k,v in snapshot.items() if k not in ('players','teams')}}
    result['lineSnapshot']['compatible']=compatible
    mode=query.get('mode',['teams'])[0]
    stat_keys={k for r in snapshot[mode] for k in r['stats']}
    if compatible:
        indexed={r['id']:r for r in result['rows']}
        for row in snapshot[mode]:
            if row['id'] in indexed: indexed[row['id']]['stats'].update(row['stats'])
            else: result['rows'].append({**row,'stats':dict(row['stats'])})
    result['stats']=sorted(set(result['stats'])|stat_keys)
    result['sources']=[*result['sources'],snapshot['source']]
    return result
