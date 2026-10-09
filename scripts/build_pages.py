"""Build a self-contained GitHub Pages site from public NFL datasets."""
import argparse, gzip, json, shutil, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from line_stats import ARTICLES,load_line_stats
from advanced_stats import load_advanced
from tracking_stats import load_tracking

def build(output, seasons, refresh=False):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    for source in (server.ROOT/'static').iterdir():
        if source.is_file(): shutil.copy2(source,output/source.name)
    (output/'.nojekyll').touch()
    target=output/'data';target.mkdir(exist_ok=True)
    available=[];failed=[];line_seasons=[];advanced_seasons=[];tracking_seasons=[]
    # Supplemental joins and base snapshots must use the same refreshed NFL data.
    if server.CURRENT in seasons: server.load(server.CURRENT,refresh)
    for season in seasons:
        if season not in ARTICLES: continue
        try:
            lines=load_line_stats(season,refresh and season==server.CURRENT)
            (target/f'lines-{season}.json').write_text(json.dumps(lines,separators=(',',':')))
            line_seasons.append(season)
            print(f'Line stats {season}: {len(lines["players"])} published players',flush=True)
        except Exception as error:
            if (target/f'lines-{season}.json').exists(): line_seasons.append(season)
            print(f'Line stats {season} unavailable: {error}',file=sys.stderr,flush=True)
    for season in seasons:
        if season<2018: continue
        path=target/f'advanced-{season}.json.gz'
        if path.exists() and season!=server.CURRENT:
            advanced_seasons.append(season);continue
        try:
            extra=load_advanced(season,refresh and season==server.CURRENT)
            if extra:
                with gzip.open(path,'wt',compresslevel=6) as f: json.dump(extra,f,separators=(',',':'),allow_nan=False)
                advanced_seasons.append(season)
                print(f'Advanced stats {season}: {len(extra["slices"])} weekly slices',flush=True)
        except Exception as error:
            if path.exists(): advanced_seasons.append(season)
            print(f'Advanced stats {season} unavailable: {error}',file=sys.stderr,flush=True)
    for season in seasons:
        path=target/f'tracking-{season}.json.gz'
        if path.exists() and season!=server.CURRENT:
            with gzip.open(path,'rt') as f: cached=json.load(f)
            if cached.get('formatVersion')==1:
                tracking_seasons.append(season);continue
        try:
            extra=load_tracking(season,refresh and season==server.CURRENT)
            with gzip.open(path,'wt',compresslevel=6) as f: json.dump(extra,f,separators=(',',':'),allow_nan=False)
            tracking_seasons.append(season)
            print(f'Tracking / nflfastR {season}: {len(extra["slices"])} slices',flush=True)
        except Exception as error:
            if path.exists():tracking_seasons.append(season)
            print(f'Tracking {season} unavailable: {error}',file=sys.stderr,flush=True)
    for season in seasons:
        path=target/f'{season}.json.gz'
        if path.exists() and season!=server.CURRENT:
            available.append(season);continue
        try:
            raw=server.load(season)
            slices=[]
            pairs=sorted({(int(r['week']),r['season_type']) for r in raw['players']})
            for week,typ in pairs:
                query={'season':[str(season)],'weekStart':[str(week)],'weekEnd':[str(week)],'seasonType':[typ],'includeLines':['0'],'includeAdvanced':['0'],'includeTracking':['0']}
                teams=server.aggregate({**query,'mode':['teams']})
                players=server.aggregate({**query,'mode':['players']})
                slices.append({'week':week,'type':typ,'teams':teams['rows'],'players':players['rows'],'plays':teams['plays']})
            payload={'season':season,'updated':raw['updated'],'slices':slices,'sources':teams['sources']}
            with gzip.open(path,'wt',compresslevel=6) as f: json.dump(payload,f,separators=(',',':'),allow_nan=False)
            available.append(season)
            print(f'Built {season}: {len(slices)} weeks, {path.stat().st_size:,} bytes',flush=True)
        except Exception as e:
            if path.exists(): available.append(season)
            else: failed.append(season)
            print(f'Season {season}: {e}',file=sys.stderr,flush=True)
    if server.CURRENT not in available: raise RuntimeError('Current-season data must be available before publishing')
    from college_stats import load_college
    college_seasons=[]
    for year in seasons:
        if year<2004:continue
        path=target/f'college-{year}.json.gz'
        try:
            if not path.exists() or year==server.CURRENT:
                payload=load_college(year,refresh and year==server.CURRENT)
                with gzip.open(path,'wt',compresslevel=6) as f:json.dump(payload,f,separators=(',',':'),allow_nan=False)
            college_seasons.append(year)
            print(f'College {year}: {path.stat().st_size:,} bytes',flush=True)
        except Exception as error:
            if path.exists():college_seasons.append(year)
            print(f'College {year} unavailable: {error}',file=sys.stderr,flush=True)
    if server.CURRENT not in college_seasons:raise RuntimeError('Current college season unavailable')
    manifest={'collegeSeasons':college_seasons,'currentSeason':server.CURRENT,'seasons':sorted(available,reverse=True),'unavailableSeasons':failed,'builtAt':time.time(),'lineSeasons':line_seasons,'advancedSeasons':advanced_seasons,'trackingSeasons':tracking_seasons}
    (target/'config.json').write_text(json.dumps(manifest))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='dist');parser.add_argument('--seasons',nargs='+',type=int);parser.add_argument('--refresh',action='store_true');args=parser.parse_args()
    build(args.output,args.seasons or list(range(server.CURRENT,1998,-1)),args.refresh)
