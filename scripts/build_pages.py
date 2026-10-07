"""Build a self-contained GitHub Pages site from public NFL datasets."""
import argparse, gzip, json, shutil, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

def build(output, seasons, refresh=False):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    for source in (server.ROOT/'static').iterdir():
        if source.is_file(): shutil.copy2(source,output/source.name)
    (output/'.nojekyll').touch()
    target=output/'data';target.mkdir(exist_ok=True)
    available=[];failed=[]
    for season in seasons:
        path=target/f'{season}.json.gz'
        if path.exists() and season!=server.CURRENT:
            available.append(season);continue
        try:
            raw=server.load(season,refresh and season==server.CURRENT)
            slices=[]
            pairs=sorted({(int(r['week']),r['season_type']) for r in raw['players']})
            for week,typ in pairs:
                query={'season':[str(season)],'weekStart':[str(week)],'weekEnd':[str(week)],'seasonType':[typ]}
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
    manifest={'currentSeason':server.CURRENT,'seasons':sorted(available,reverse=True),'unavailableSeasons':failed,'builtAt':time.time()}
    (target/'config.json').write_text(json.dumps(manifest))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='dist');parser.add_argument('--seasons',nargs='+',type=int);parser.add_argument('--refresh',action='store_true');args=parser.parse_args()
    build(args.output,args.seasons or list(range(server.CURRENT,1998,-1)),args.refresh)
