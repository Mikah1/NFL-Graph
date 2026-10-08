"""Weekly PFR game-charting imports from public nflverse releases.

Only supplemental metrics are exposed. Contact means defender contact on a rush;
receiving yards after catch remains the existing, separate nflverse metric.
"""
import csv, math, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

SOURCE={'name':'nflverse / Pro Football Reference advanced game charting','url':'https://github.com/nflverse/nflverse-data/releases/tag/pfr_advstats'}
ORIGIN='https://www.pro-football-reference.com/about/advanced_stats.htm'
KINDS=('rush','pass','rec','def')
FIELDS={
 'rush':{'rushing_yards_before_contact':'rushing_yards_before_contact','rushing_yards_after_contact':'rushing_yards_after_contact','rushing_broken_tackles':'rushing_broken_tackles'},
 'pass':{'passing_drops':'passing_drops','passing_bad_throws':'passing_bad_throws','times_blitzed':'passing_times_blitzed','times_hurried':'passing_times_hurried','times_hit':'passing_times_hit','times_pressured':'passing_times_pressured'},
 'rec':{'receiving_broken_tackles':'receiving_broken_tackles','receiving_drop':'receiving_drops','receiving_int':'receiving_interceptions_on_targets'},
 'def':{'def_targets':'def_targets','def_completions_allowed':'def_completions_allowed','def_yards_allowed':'def_yards_allowed','def_receiving_td_allowed':'def_receiving_tds_allowed','def_air_yards_completed':'def_air_yards_completed','def_yards_after_catch':'def_yards_after_catch_allowed','def_times_blitzed':'def_blitzes','def_times_hurried':'def_hurries','def_pressures':'def_pressures','def_missed_tackles':'def_missed_tackles'},
}
# Counts-prefixed denominators are private sample sizes, never duplicate picker stats.
RATIOS={
 'rushing_yards_before_contact_per_carry':['rushing_yards_before_contact','@rush_carries',1],
 'rushing_yards_after_contact_per_carry':['rushing_yards_after_contact','@rush_carries',1],
 'rushing_broken_tackle_rate':['rushing_broken_tackles','@rush_carries',100],
 'rushing_carries_per_broken_tackle':['@rush_carries','rushing_broken_tackles',1],
 'receiving_broken_tackle_rate':['receiving_broken_tackles','@rec_catches',100],
 'receiving_drop_pct':['receiving_drops','@rec_targets',100],
 'def_completion_pct_allowed':['def_completions_allowed','def_targets',100],
 'def_yards_per_target_allowed':['def_yards_allowed','def_targets',1],
 'def_yards_per_completion_allowed':['def_yards_allowed','def_completions_allowed',1],
 'def_average_depth_of_target':['@def_target_air_yards','def_targets',1],
 'def_yards_after_catch_allowed_per_completion':['def_yards_after_catch_allowed','def_completions_allowed',1],
 'def_missed_tackle_pct':['def_missed_tackles','@def_tackle_opportunities',100],
}
TEAM_ALIASES={'KAN':'KC','GNB':'GB','NWE':'NE','NOR':'NO','SFO':'SF','TAM':'TB','LVR':'LV'}
memory={}

def number(value):
    try:
        value=float(value)
        return value if math.isfinite(value) else None
    except (TypeError,ValueError): return None

def season_type(value):
    return 'POST' if value in ('WC','DIV','CON','SB','PST','POST') else value

def read_csv(path):
    with path.open() as f: return list(csv.DictReader(f))

def passer_rating(attempts,completions,yards,touchdowns,interceptions):
    if not attempts: return None
    parts=[(completions/attempts-.3)*5,(yards/attempts-3)*.25,touchdowns/attempts*20,2.375-interceptions/attempts*25]
    return sum(max(0,min(2.375,p)) for p in parts)/6*100

def derive(stats,counts,ratios=None):
    def value(key): return counts.get(key[1:]) if key.startswith('@') else stats.get(key)
    for key,(numerator,denominator,scale) in (RATIOS if ratios is None else ratios).items():
        n=value(numerator);d=value(denominator)
        if n is not None: stats[key]=n/d*scale if d else None
    if all(k in stats for k in ['def_targets','def_completions_allowed','def_yards_allowed','def_receiving_tds_allowed']) and 'def_interceptions' in counts:
        stats['def_passer_rating_allowed']=passer_rating(stats['def_targets'],stats['def_completions_allowed'],stats['def_yards_allowed'],stats['def_receiving_tds_allowed'],counts['def_interceptions'])
    if all(k in counts for k in ['rec_targets','rec_catches','rec_yards','rec_tds']) and 'receiving_interceptions_on_targets' in stats:
        stats['receiving_passer_rating_when_targeted']=passer_rating(counts['rec_targets'],counts['rec_catches'],counts['rec_yards'],counts['rec_tds'],stats['receiving_interceptions_on_targets'])
    if 'ngs_passing_completed_air_yards' in stats and 'ngs_passing_intended_air_yards' in stats:
        stats['ngs_passing_air_yards_differential']=stats['ngs_passing_completed_air_yards']-stats['ngs_passing_intended_air_yards']
    for key,value in stats.items():
        if value is not None: stats[key]=round(value,4)
    return stats

def prepare(season,feeds,identities,base_players,team_info,updated):
    identities={r['pfr_id']:r for r in identities if r.get('pfr_id') and r.get('gsis_id')}
    base={(r['game_id'],r['player_id']):r for r in base_players}
    slices={};coverage=[]
    for kind,entries in feeds.items():
        valid=[r for r in entries if number(r.get('season'))==season]
        weeks=sorted({int(r['week']) for r in valid});types=sorted({season_type(r['game_type']) for r in valid})
        coverage.append({'category':kind,'weeks':weeks,'seasonTypes':types,'weeksByType':{t:sorted({int(r['week']) for r in valid if season_type(r['game_type'])==t}) for t in types},'records':len(valid)})
        seen=set()
        for source in valid:
            week=int(source['week']);typ=season_type(source['game_type']);pfr=source['pfr_player_id'];dedup=(source['game_id'],pfr)
            if dedup in seen: continue
            seen.add(dedup)
            identity=identities.get(pfr,{})
            pid=identity.get('gsis_id') or 'pfr:'+pfr
            standard=base.get((source['game_id'],pid),{})
            info=team_info(TEAM_ALIASES.get(source['team'],source['team']))
            slice_=slices.setdefault((week,typ),{'week':week,'type':typ,'players':{},'teams':{}})
            name=source['pfr_player_name']
            row=slice_['players'].setdefault(pid,{**info,'id':pid,'name':name,'short':identity.get('short_name') or name,'position':standard.get('position') or identity.get('position') or 'UNK','logo':standard.get('headshot_url') or identity.get('headshot') or '', 'stats':{},'counts':{},'_games':set()})
            stats={key:value for field,key in FIELDS[kind].items() if (value:=number(source.get(field))) is not None}
            if not stats: continue
            counts={}
            if kind=='rush':
                carries=number(source.get('carries'))
                if carries is not None: counts['rush_carries']=carries
            elif kind=='pass':
                if (attempts:=number(standard.get('attempts'))) is not None: counts['pass_attempts']=attempts
            elif kind=='rec':
                for field,key in [('targets','rec_targets'),('receptions','rec_catches'),('receiving_yards','rec_yards'),('receiving_tds','rec_tds')]:
                    value=number(standard.get(field))
                    if value is not None: counts[key]=value
            elif kind=='def':
                combined=number(source.get('def_tackles_combined'));missed=number(source.get('def_missed_tackles'));targets=number(source.get('def_targets'));adot=number(source.get('def_adot'));ints=number(source.get('def_ints'))
                if combined is not None and missed is not None: counts['def_tackle_opportunities']=combined+missed
                if targets is not None: counts['def_targets']=targets
                if targets is not None and adot is not None: counts['def_target_air_yards']=targets*adot
                if ints is not None: counts['def_interceptions']=ints
            for key,value in stats.items(): row['stats'][key]=row['stats'].get(key,0)+value
            for key,value in counts.items(): row['counts'][key]=row['counts'].get(key,0)+value
            row['_games'].add(source['game_id'])
            team=slice_['teams'].setdefault(info['team'],{**info,'id':info['team'],'position':'TEAM','stats':{},'counts':{},'_games':set()})
            for key,value in stats.items(): team['stats'][key]=team['stats'].get(key,0)+value
            for key,value in counts.items(): team['counts'][key]=team['counts'].get(key,0)+value
            team['_games'].add(source['game_id'])
    for slice_ in slices.values():
        for mode in ('players','teams'):
            slice_[mode]=[r for r in slice_[mode].values() if r['stats']]
            for row in slice_[mode]: row['chartedGames']=len(row.pop('_games'));derive(row['stats'],row['counts'])
    return {'season':season,'updated':updated,'source':SOURCE,'origin':ORIGIN,'coverage':coverage,'ratios':RATIOS,'slices':list(slices.values())}

def load_advanced(season,refresh=False):
    import server
    if not 2018<=season<=server.CURRENT: return None
    cached=memory.get(season)
    if cached and not refresh and time.time()-cached['loaded']<21600: return cached['data']
    with ThreadPoolExecutor(max_workers=5) as pool:
        jobs={kind:pool.submit(server.fetch,f'advstats_week_{kind}_{season}.csv',f'{server.BASE}/pfr_advstats/advstats_week_{kind}_{season}.csv',refresh) for kind in KINDS}
        ids_job=pool.submit(server.fetch,'identities.csv',f'{server.BASE}/players/players.csv',refresh)
        feeds={};paths=[]
        for kind,job in jobs.items():
            try:
                path=job.result();rows=read_csv(path)
                if rows and all(field in rows[0] for field in ['season','week','game_type','pfr_player_id',*FIELDS[kind]]): feeds[kind]=rows;paths.append(path)
            except Exception: pass
        identities=read_csv(ids_job.result())
    if not feeds: return None
    raw=server.load(season);result=prepare(season,feeds,identities,raw['players'],lambda a:server.team_info(a,raw['teams']),min(p.stat().st_mtime for p in paths))
    if not result['slices']: return None
    if len(memory)>=3: memory.pop(next(iter(memory)))
    memory[season]={'loaded':time.time(),'data':result}
    return result

def merge_advanced(result,data,query,metadata_key="advancedCoverage"):
    if not data: return result
    ratios=data.get("ratios",RATIOS);max_stats=set(data.get("maxStats",[]))
    low=int(query.get('weekStart',['1'])[0]);high=int(query.get('weekEnd',['22'])[0]);typ=query.get('seasonType',['REG'])[0];mode=query.get('mode',['teams'])[0]
    selected=[s for s in data['slices'] if low<=s['week']<=high and (typ=='ALL' or s['type']==typ)]
    grouped={}
    for slice_ in selected:
        for row in slice_[mode]:
            group=grouped.setdefault(row['id'],{**row,'stats':{},'counts':{},'chartedGames':0})
            group['chartedGames']+=row['chartedGames']
            for key,value in row['stats'].items():
                if key not in ratios and key not in ('def_passer_rating_allowed','receiving_passer_rating_when_targeted','ngs_passing_air_yards_differential') and value is not None: group['stats'][key]=max(group['stats'].get(key,float('-inf')),value) if key in max_stats else group['stats'].get(key,0)+value
            for key,value in row['counts'].items(): group['counts'][key]=group['counts'].get(key,0)+value
    result={**result,'rows':[{**r,'stats':dict(r['stats'])} for r in result['rows']], 'sources':[*result['sources'],data['source']]}
    indexed={r['id']:r for r in result['rows']}
    keys={k for s in data['slices'] for r in s[mode] for k in r['stats']}
    for pid,row in grouped.items():
        derive(row['stats'],row['counts'],ratios)
        target=indexed.get(pid)
        if target is None:
            target={k:v for k,v in row.items() if k not in ('counts','chartedGames')};target['stats']['games']=row['chartedGames'];result['rows'].append(target)
        # Existing metrics always take precedence; do not expose renamed copies.
        target['stats'].update({k:v for k,v in row['stats'].items() if k not in target['stats']})
        target['advancedSamples']={**target.get('advancedSamples',{}),**row['counts']}
    result['stats']=sorted(set(result['stats'])|keys)
    result[metadata_key]={'updated':data['updated'],'categories':data['coverage'],'selectedWeeks':sorted({s['week'] for s in selected}),'source':data['source']}
    return result
