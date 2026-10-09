"""Key-free college football imports from sportsdataverse's ESPN game feeds."""
import csv, time, threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from advanced_stats import merge_advanced, derive

SOURCE='https://github.com/sportsdataverse/cfbfastR-cfb-data'
_lock=threading.Lock()
_memory={}

def load_college(year,refresh=False):
    import server
    with _lock:
        if not refresh and year in _memory and time.time()-_memory[year]['updated']<21600:return _memory[year]
        names={'teams':'cfb_teams','schedules':'cfb_schedule','player_box':'player_box','adv_team':'adv_team','adv_passing':'adv_passing','adv_rushing':'adv_rushing','adv_receiving':'adv_receiving','adv_defensive':'adv_defensive'}
        def read(item):
            tag,file=item;url=f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_{tag}/{file}_{year}.csv'
            path=server.fetch(f'college-{tag}-{year}.csv',url,refresh)
            with path.open(encoding='utf-8-sig',newline='') as f:return tag,list(csv.DictReader(f))
        with ThreadPoolExecutor(max_workers=8) as pool: feeds=dict(pool.map(read,names.items()))
        payload=prepare(year,feeds)
        if len(_memory)>=3:_memory.pop(next(iter(_memory)))
        _memory[year]=payload
        return payload

def prepare(year,feeds):
    from server import number
    teams={r['team_id']:r for r in feeds['teams']}
    games={r['game_id']:r for r in feeds['schedules'] if r['status']=='STATUS_FINAL' and r['season_type'] in ('2','3')}
    slices={};ratios={};seen=defaultdict(set);names={}
    def ratio(key,num,den,scale=1):ratios[key]=[num,den,scale]
    def row(game,tid,pid=None,name='',position=''):
        schedule=games[game];pair=(int(schedule['week']),'POST' if schedule['season_type']=='3' else 'REG')
        s=slices.setdefault(pair,{'week':pair[0],'type':pair[1],'players':{},'teams':{}});t=teams.get(tid,{})
        key=str(pid or tid);mode='players' if pid else 'teams'
        if key not in s[mode]:
            full=name if pid else t.get('display_name',tid)
            s[mode][key]={'id':key,'name':full,'short':''.join(w[0] for w in full.split() if w),'team':t.get('display_name',tid),'conference':t.get('conference_short_name') or t.get('conference_name','Independent'),'position':position,'logo':t.get('team_logo',f'https://a.espncdn.com/i/teamlogos/ncaa/500/{tid}.png'),'stats':{},'counts':{},'chartedGames':0}
        r=s[mode][key];identity=(pair,mode,key)
        if game not in seen[identity]:seen[identity].add(game);r['chartedGames']+=1
        if pid and not r['position']:r['position']=position
        return r
    def add(r,key,v):
        n=number(v)
        if n is not None:r['stats'][key]=r['stats'].get(key,0)+n
    boxmap={'rushingAttempts':'carries','rushingYards':'rushing_yards','rushingTouchdowns':'rushing_tds','receptions':'receptions','receivingYards':'receiving_yards','receivingTouchdowns':'receiving_tds','totalTackles':'def_tackles_total','soloTackles':'def_tackles_solo','sacks':'def_sacks','tacklesForLoss':'def_tackles_for_loss','passesDefended':'def_passes_defended','hurries':'def_hurries','defensiveTouchdowns':'def_touchdowns','interceptions':'def_interceptions','interceptionYards':'def_interception_yards','kickReturns':'kick_returns','kickReturnYards':'kick_return_yards','kickReturnTouchdowns':'kick_return_tds','punts':'pt_att','puntYards':'pt_yards','touchbacks':'pt_touchbacks','puntsInside20':'pt_inside20','puntReturns':'punt_returns','puntReturnYards':'punt_return_yards','puntReturnTouchdowns':'punt_return_tds','fumbles':'fumbles','fumblesLost':'fumbles_lost','fumblesRecovered':'fumbles_recovered'}
    for b in feeds['player_box']:
        game=b['game_id'];tid=b['team_id']
        if game not in games:continue
        pid=b['athlete_id'];name=b['athlete_name'];names[(game,tid,name)]=pid
        pos={'passing':'QB','rushing':'RB','receiving':'WR','defensive':'DEF','interceptions':'DEF','kicking':'K','punting':'P'}.get(b['category'],'')
        r=row(game,tid,pid,name,pos)
        for field,key in boxmap.items():add(r,key,b.get(field))
        for field,key in [('longRushing','rushing_long'),('longReception','receiving_long'),('longFieldGoalMade','fg_long'),('longPunt','pt_long')]:
            v=number(b.get(field))
            if v is not None:r['stats'][key]=max(r['stats'].get(key,0),v)
        if b['category']=='passing':
            compatt=b.get('completions/passingAttempts') or b['stat_1']
            if '/' in compatt:
                c,a=compatt.split('/');add(r,'completions',c);add(r,'attempts',a)
            for key,field,fallback in [('passing_yards','passingYards','stat_2'),('passing_tds','passingTouchdowns','stat_4'),('passing_interceptions','', 'stat_5')]:add(r,key,b.get(field) or b.get(fallback))
        for field,a,c in [('fieldGoalsMade/fieldGoalAttempts','fg_att','fg_made'),('extraPointsMade/extraPointAttempts','pat_att','pat_made')]:
            v=b.get(field,'')
            if '/' in v:
                made,att=v.split('/');add(r,c,made);add(r,a,att)
    teammap={'scrimmage_plays':'off_plays','EPA_overall_off':'off_epa_total','rushes':'off_rush_plays','passes':'off_pass_plays','rush_yards':'off_rush_yards','pass_yards':'off_pass_yards','off_yards':'off_yards','EPA_rushing_overall':'off_rush_epa_total','EPA_passing_overall':'off_pass_epa_total','EPA_explosive':'off_explosive_plays','first_downs_created':'off_first_downs','rushing_stuff':'rushing_stuffed_plays','rushing_opportunity':'rushing_opportunity_plays','rushing_power':'rushing_power_plays','rushing_power_success':'rushing_power_successes','rushing_highlight_yards':'rushing_highlight_yards','line_yards':'rushing_line_yards','second_level_yards':'rushing_second_level_yards','open_field_yards':'rushing_open_field_yards','total_pen_yards':'off_penalty_yards','EPA_penalty':'off_penalty_epa','special_teams_plays':'special_teams_plays','EPA_special_teams':'special_teams_epa','EPA_fg':'fg_epa','EPA_punt':'pt_epa','EPA_kickoff':'kickoff_epa'}
    for b in feeds['adv_team']:
        game=b['game_id'];tid=b['pos_team_id']
        if game not in games:continue
        r=row(game,tid);schedule=games[game];other=schedule['away_id'] if tid==schedule['home_id'] else schedule['home_id'];d=row(game,other)
        for field,key in teammap.items():
            add(r,key,b.get(field))
            if key.startswith('off_'):add(d,key.replace('off_','def_',1),b.get(field))
    for family,role,den in [('passing','passer','Att'),('rushing','rusher','Car'),('receiving','receiver','Tar')]:
        for b in feeds['adv_'+family]:
            game=b['game_id'];tid=b['pos_team_id'];name=b[role+'_player_name']
            if game not in games:continue
            pid=names.get((game,tid,name))
            if not pid:continue # Never join different athletes by surname alone.
            r=row(game,tid,pid,name);add(r,family+'_epa',b.get('EPA'));add(r,family+'_wpa',b.get('WPA'))
            if family=='receiving':add(r,'targets',b.get('Tar'))
            if family=='passing':
                add(r,'passing_air_yards',b.get('AirYds'));add(r,'passing_completed_air_yards',b.get('CompAirYds'));add(r,'passing_yards_after_catch',b.get('YAC'));add(r,'passing_expected_completions',b.get('xComp'));add(r,'passing_sacks',b.get('Sck'))
            if family=='receiving':
                add(r,'receiving_air_yards',b.get('AirYds'));add(r,'receiving_yards_after_catch',b.get('YAC'))
            count=number(b.get(den));sr=number(b.get('SR'))
            if count is not None and sr is not None:
                # Passing SR includes sacks in the provider's dropback denominator.
                plays=count+(number(b.get('Sck')) or 0) if family=='passing' else count
                add(r,family+'_successes',sr*plays);add(r,family+'_plays',plays)
                if family!='receiving':
                    t=row(game,tid);add(t,'off_successes',sr*plays);schedule=games[game];other=schedule['away_id'] if tid==schedule['home_id'] else schedule['home_id'];add(row(game,other),'def_successes',sr*plays)
    for b in feeds['adv_defensive']:
        if b['game_id'] not in games:continue
        r=row(b['game_id'],b['def_pos_team_id'])
        for field,key in {'TFL':'def_tackles_for_loss','havoc_total':'def_havoc_plays','sacks':'def_sacks','pass_breakups':'def_passes_defended','def_int':'def_interceptions','num_pass_plays':'def_dropbacks'}.items():add(r,key,b.get(field))
    for key,num,den,scale in [('completion_pct','completions','attempts',100),('yards_per_attempt','passing_yards','attempts',1),('yards_per_carry','rushing_yards','carries',1),('yards_per_reception','receiving_yards','receptions',1),('catch_pct','receptions','targets',100),('fg_pct','fg_made','fg_att',100),('pat_pct','pat_made','pat_att',100),('pt_average','pt_yards','pt_att',1),('passing_cpoe','passing_completion_residual','attempts',100),('receiving_average_depth_of_target','receiving_air_yards','targets',1),('receiving_yards_after_catch_per_reception','receiving_yards_after_catch','receptions',1)]:ratio(key,num,den,scale)
    for family,den in [('passing','attempts'),('rushing','carries'),('receiving','targets')]:
        ratio(family+'_epa_per_'+{'passing':'dropback','rushing':'carry','receiving':'target'}[family],family+'_epa',den);ratio(family+'_success_rate',family+'_successes',family+'_plays',100)
    for side in ['off','def']:
        for suffix,num,den,scale in [('epa_per_play','epa_total','plays',1),('success_rate','successes','plays',100),('yards_per_play','yards','plays',1),('explosive_rate','explosive_plays','plays',100),('pass_rate','pass_plays','plays',100),('pass_epa','pass_epa_total','pass_plays',1),('rush_epa','rush_epa_total','rush_plays',1)]:ratio(side+'_'+suffix,side+'_'+num,side+'_'+den,scale)
        ratio(side+'_yards_per_game',side+'_yards','@games');
    for suffix,num,den,scale in [('line_yards_per_carry','line_yards','off_rush_plays',1),('stuff_rate','stuffed_plays','off_rush_plays',100),('opportunity_rate','opportunity_plays','off_rush_plays',100),('power_success_rate','power_successes','rushing_power_plays',100)]:ratio('rushing_'+suffix,'rushing_'+num,den,scale)
    ratio('def_sack_pct','def_sacks','def_dropbacks',100);ratio('def_havoc_rate','def_havoc_plays','def_plays',100)
    # Standard offensive fantasy scoring; defensive and kicking fantasy are not inferred.
    for s in slices.values():
        for r in s['players'].values():
            st=r['stats']
            if not any(k in st for k in ['attempts','carries','receptions']):continue
            st['total_yards']=sum(st.get(k,0) for k in ['passing_yards','rushing_yards','receiving_yards'])
            st['touchdowns']=sum(st.get(k,0) for k in ['passing_tds','rushing_tds','receiving_tds'])
            st['fantasy_points']=st.get('passing_yards',0)*.04+st.get('passing_tds',0)*4-st.get('passing_interceptions',0)*2+(st.get('rushing_yards',0)+st.get('receiving_yards',0))*.1+(st.get('rushing_tds',0)+st.get('receiving_tds',0))*6-st.get('fumbles_lost',0)*2
            st['fantasy_points_ppr']=st['fantasy_points']+st.get('receptions',0)
    result=[]
    for s in slices.values():
        for mode in ['teams','players']:
            for r in s[mode].values():
                r['counts']['games']=r['chartedGames']
                r['stats']['games']=r['chartedGames']
                if 'passing_expected_completions' in r['stats']:r['stats']['passing_completion_residual']=r['stats'].get('completions',0)-r['stats']['passing_expected_completions']
            for r in s[mode].values():derive(r['stats'],r['counts'],ratios)
            s[mode]=list(s[mode].values())
        result.append(s)
    extra={'maxStats':['rushing_long','receiving_long','fg_long','pt_long'],'updated':time.time(),'source':SOURCE,'coverage':[],'ratios':ratios,'slices':result}
    if not result:raise ValueError(f'No completed college games published for {year}')
    return {'league':'college','season':year,'updated':extra['updated'],'sources':[SOURCE,'https://github.com/sportsdataverse/sportsdataverse-data'],'slices':[{'week':s['week'],'type':s['type'],'teams':[],'players':[],'plays':sum(r['stats'].get('off_plays',0) for r in s['teams'])} for s in result],'advanced':extra}

def aggregate_college(q):
    from server import CURRENT
    year=int(q.get('season',[str(CURRENT)])[0]);source=load_college(year,q.get('refresh',['0'])[0]=='1')
    result={'rows':[],'stats':[],'season':year,'updated':source['updated'],'stale':time.time()-source['updated']>21600,'sources':source['sources'],'weeks':sorted({s['week'] for s in source['slices']}),'plays':sum(s['plays'] for s in source['slices'] if int(q.get('weekStart',['1'])[0])<=s['week']<=int(q.get('weekEnd',['22'])[0]) and q.get('seasonType',['REG'])[0] in ('ALL',s['type']))}
    result=merge_advanced(result,source['advanced'],q)
    result['advancedCoverage']=None
    return result
