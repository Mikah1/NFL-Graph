"""Missing nflfastR play-by-play metrics and weekly NFL Next Gen tracking."""
import csv,gzip,time
from concurrent.futures import ThreadPoolExecutor
from advanced_stats import number,derive
SOURCE={'name':'nflfastR + NFL Next Gen Stats via nflverse','url':'https://github.com/nflverse/nflverse-data/releases/tag/nextgen_stats'}
PBP_FIELDS='passer_player_id receiver_player_id rusher_player_id passer_player_name receiver_player_name rusher_player_name wpa qb_epa air_epa yac_epa comp_air_epa comp_yac_epa air_yards yards_after_catch complete_pass sack qb_scramble qb_kneel qb_spike xpass pass_oe third_down_converted fourth_down_converted'.split()
# field, output key, weight (None = sum; max = season maximum)
NGS={
 'passing':[
 ('avg_time_to_throw','ngs_passing_time_to_throw','attempts'),('avg_completed_air_yards','ngs_passing_completed_air_yards','completions'),('avg_intended_air_yards','ngs_passing_intended_air_yards','attempts'),('aggressiveness','ngs_passing_tight_window_pct','attempts'),('max_completed_air_distance','ngs_passing_max_completed_air_distance','max'),('avg_air_yards_to_sticks','ngs_passing_air_yards_to_sticks','attempts'),('expected_completion_percentage','ngs_passing_expected_completion_pct','attempts'),('avg_air_distance','ngs_passing_air_distance','attempts'),('max_air_distance','ngs_passing_max_air_distance','max')],
 'rushing':[
 ('efficiency','ngs_rushing_efficiency','rush_yards'),('percent_attempts_gte_eight_defenders','ngs_rushing_stacked_box_pct','rush_attempts'),('avg_time_to_los','ngs_rushing_time_to_los','rush_attempts'),('expected_rush_yards','ngs_rushing_expected_yards',None),('rush_yards_over_expected','ngs_rushing_yards_over_expected',None),('rush_pct_over_expected','ngs_rushing_over_expected_pct','rush_attempts')],
 'receiving':[
 ('avg_cushion','ngs_receiving_cushion','targets'),('avg_separation','ngs_receiving_separation','targets'),('avg_expected_yac','ngs_receiving_expected_yac_per_reception','receptions'),('avg_yac_above_expectation','ngs_receiving_yac_over_expected_per_reception','receptions')],
}
memory={}

def prepare(season,raw,feeds,updated):
    import server
    slices={};ratios={};max_stats=[];coverage=[]
    identities={r['player_id']:r for r in raw['players']}
    def row(week,typ,mode,pid,team,name='',position=''):
        s=slices.setdefault((week,typ),{'week':week,'type':typ,'players':{},'teams':{}})
        if pid not in s[mode]:
            identity=identities.get(pid,{}) if mode=='players' else {}
            s[mode][pid]={**server.team_info(team,raw['teams']),'id':pid,'name':(server.team_info(team,raw['teams'])['name'] if mode=='teams' else identity.get('player_display_name') or name or team),'short':identity.get('player_name') or name or team,'position':identity.get('position') or position or ('TEAM' if mode=='teams' else 'UNK'),'logo':server.team_info(team,raw['teams'])['logo'] if mode=='teams' else identity.get('headshot_url',''),'stats':{},'counts':{},'chartedGames':1}
        return s[mode][pid]
    def add(r,key,value):
        if value is not None:r['stats'][key]=r['stats'].get(key,0)+value
    def count(r,key,value):r['counts'][key]=r['counts'].get(key,0)+value
    def ratio(key,num,den,scale=1):ratios[key]=[num,den,scale]
    pbp_weeks=set()
    for p in raw['plays']:
        if p['play_type'] not in ('pass','run') or not p['posteam']:continue
        week=int(p['week']);typ=p['season_type'];pbp_weeks.add(week)
        off=row(week,typ,'teams',server.ALIASES.get(p['posteam'],p['posteam']),p['posteam']);defense=row(week,typ,'teams',server.ALIASES.get(p['defteam'],p['defteam']),p['defteam']) if p['defteam'] else None
        wpa=number(p.get('wpa'));drop=number(p.get('qb_dropback'))==1;sack=number(p.get('sack'))==1
        for side,r in [('off',off),('def',defense)]:
            if r is None:continue
            add(r,side+'_wpa',wpa*(1 if side=='off' else -1) if wpa is not None else None)
            if drop:
                add(r,side+'_dropbacks',1);add(r,side+'_sacks',int(sack));ratio(side+'_sack_pct',side+'_sacks',side+'_dropbacks',100)
            for down in [3,4]:
                if number(p.get('down'))==down:
                    add(r,f'{side}_{down}down_attempts',1);add(r,f'{side}_{down}down_conversions',number(p.get('third_down_converted' if down==3 else 'fourth_down_converted')) or 0);ratio(f'{side}_{down}down_conversion_pct',f'{side}_{down}down_conversions',f'{side}_{down}down_attempts',100)
            if number(p.get('yardline_100')) is not None and float(p['yardline_100'])<=20:
                epa=number(p.get('epa'))
                if epa is not None:
                    add(r,side+'_red_zone_epa',epa);count(r,side+'_red_zone_plays',1);ratio(side+'_red_zone_epa_per_play',side+'_red_zone_epa','@'+side+'_red_zone_plays')
        xpass=number(p.get('xpass'));poe=number(p.get('pass_oe'))
        if xpass is not None:count(off,'off_expected_pass_sum',xpass);count(off,'off_expected_pass_n',1);ratio('off_expected_pass_pct','@off_expected_pass_sum','@off_expected_pass_n',100)
        if poe is not None:count(off,'off_pass_oe_sum',poe);count(off,'off_pass_oe_n',1);ratio('off_pass_rate_over_expected','@off_pass_oe_sum','@off_pass_oe_n')
        for role,prefix in [('passer','passing'),('rusher','rushing'),('receiver','receiving')]:
            pid=p.get(role+'_player_id')
            if role=='passer' and drop and number(p.get('qb_scramble'))==1:pid=pid or p.get('rusher_player_id')
            if not pid:continue
            r=row(week,typ,'players',pid,p['posteam'],p.get(role+'_player_name',''));count(r,'pbp_'+prefix+'_plays',1)
            add(r,prefix+'_wpa',wpa)
            if prefix=='passing' and drop:
                add(r,'rushing_scrambles',0)
                qbe=number(p.get('qb_epa'))
                if qbe is not None:count(r,'pbp_qb_dropbacks',1);add(r,'passing_qb_epa',qbe)
                ratio('passing_qb_epa_per_dropback','passing_qb_epa','@pbp_qb_dropbacks')
                for field,key in [('air_epa','passing_air_epa'),('yac_epa','passing_yac_epa'),('comp_air_epa','passing_completed_air_epa'),('comp_yac_epa','passing_completed_yac_epa')]:add(r,key,number(p.get(field)))
            if prefix=='rushing' and number(p.get('qb_scramble'))==1:add(r,'rushing_scrambles',1)
            if prefix=='receiving':
                air=number(p.get('air_yards'))
                if air is not None:count(r,'pbp_target_air_yards',air);count(r,'pbp_air_targets',1);ratio('receiving_average_depth_of_target','@pbp_target_air_yards','@pbp_air_targets')
                if number(p.get('complete_pass'))==1:
                    yac=number(p.get('yards_after_catch'))
                    if yac is not None:count(r,'pbp_yac',yac);count(r,'pbp_yac_receptions',1);ratio('receiving_yards_after_catch_per_reception','@pbp_yac','@pbp_yac_receptions')
    coverage.append({'category':'pbp','weeks':sorted(pbp_weeks),'weeksByType':{t:sorted({w for w,typ in slices if typ==t}) for t in ['REG','POST']},'records':len(raw['plays'])})
    for kind,entries in feeds.items():
        selected=[p for p in entries if number(p.get('season'))==season and (number(p.get('week')) or 0)>0]
        selected=[{**p,'week':str((22 if season>=2021 else 21) if p['season_type']=='POST' and int(p['week'])==(23 if season>=2021 else 22) else int(p['week']))} for p in selected]
        seen=set()
        for p in selected:
            week=int(p['week']);typ=p['season_type'];pid=p.get('player_gsis_id');team=p['team_abbr']
            if not pid or (week,typ,pid,team) in seen:continue
            seen.add((week,typ,pid,team))
            targets=[row(week,typ,'players',pid,team,p['player_display_name'],p['player_position']),row(week,typ,'teams',server.ALIASES.get(team,team),team)]
            opportunity=number(p.get({'passing':'attempts','rushing':'rush_attempts','receiving':'targets'}[kind])) or 0
            for r in targets:
                count(r,'ngs_'+kind+'_sample',opportunity)
                for field,key,weight in NGS[kind]:
                    value=number(p.get(field))
                    if value is None:continue
                    if field=='rush_pct_over_expected':value*=100
                    if weight=='max':
                        r['stats'][key]=max(r['stats'].get(key,float('-inf')),value)
                        if key not in max_stats:max_stats.append(key)
                    elif weight is None:add(r,key,value)
                    else:
                        n=number(p.get(weight))
                        if n is not None and n>0:
                            count(r,key+'_sum',value*n);count(r,key+'_weight',n);ratio(key,'@'+key+'_sum','@'+key+'_weight')
                if kind=='rushing':
                    value=number(p.get('expected_rush_yards'));actual=number(p.get('rush_yards_over_expected'));n=number(p.get('rush_attempts'))
                    for key,v in [('ngs_rushing_expected_yards_per_carry',value),('ngs_rushing_yards_over_expected_per_carry',actual)]:
                        if v is not None and n is not None:count(r,key+'_sum',v);count(r,key+'_weight',n);ratio(key,'@'+key+'_sum','@'+key+'_weight')
                if kind=='receiving':
                    for field,key in [('avg_expected_yac','ngs_receiving_expected_yac_total'),('avg_yac_above_expectation','ngs_receiving_yac_over_expected_total')]:
                        value=number(p.get(field));n=number(p.get('receptions'))
                        if value is not None and n is not None:add(r,key,value*n)
        coverage.append({'category':'ngs_'+kind,'weeks':sorted({int(p['week']) for p in selected}),'weeksByType':{t:sorted({int(p['week']) for p in selected if p['season_type']==t}) for t in ['REG','POST']},'records':len(selected)})
    for s in slices.values():
        for mode in ['teams','players']:
            s[mode]=list(s[mode].values())
            for r in s[mode]:derive(r['stats'],r['counts'],ratios)
    return {'formatVersion':1,'season':season,'updated':updated,'source':SOURCE,'coverage':coverage,'ratios':ratios,'maxStats':max_stats,'slices':list(slices.values())}

def load_tracking(season,refresh=False):
    import server
    cached=memory.get(season)
    if cached and not refresh and time.time()-cached['loaded']<21600:return cached['data']
    feeds={};paths=[]
    if season>=2016:
        with ThreadPoolExecutor(max_workers=3) as pool:
            jobs={kind:pool.submit(server.fetch,'ngs_'+kind+'.csv.gz',f'{server.BASE}/nextgen_stats/ngs_{kind}.csv.gz',refresh) for kind in NGS}
            for kind,job in jobs.items():
                try:
                    path=job.result()
                    with gzip.open(path,'rt') as f:feeds[kind]=list(csv.DictReader(f))
                    paths.append(path)
                except Exception:pass
    raw=server.load(season);data=prepare(season,raw,feeds,min([raw['updated'],*[p.stat().st_mtime for p in paths]]))
    if len(memory)>=3:memory.pop(next(iter(memory)))
    memory[season]={'loaded':time.time(),'data':data};return data
