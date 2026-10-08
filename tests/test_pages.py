import json, subprocess, tempfile, unittest
from pathlib import Path
import server
from scripts.build_pages import build

class PagesTests(unittest.TestCase):
    def test_static_build_and_worker_match_python(self):
        season=2026
        with tempfile.TemporaryDirectory() as folder:
            build(folder,[season])
            root=Path(folder)
            manifest=json.loads((root/'data/config.json').read_text())
            self.assertIn(season,manifest['seasons'])
            html=(root/'index.html').read_text()
            self.assertNotIn('href="/style.css"',html)
            self.assertIn('src="data-client.js"',html)
            self.assertTrue((root/'data-worker.js').exists())
            self.assertIn(season,manifest['lineSeasons'])
            self.assertIn(season,manifest['advancedSeasons'])
            expected={mode:server.aggregate({'season':[str(season)],'mode':[mode],'weekStart':['1'],'weekEnd':['18'],'seasonType':['REG'],'includeLines':['0'],'includeAdvanced':['0']}) for mode in ['teams','players']}
            path=root/'expected.json';path.write_text(json.dumps(expected))
            subprocess.run(['node','tests/test_data_worker.cjs',str(root/f'data/{season}.json.gz'),str(path)],check=True)
            expected={mode:server.aggregate({'season':[str(season)],'mode':[mode],'weekStart':['1'],'weekEnd':['18'],'seasonType':['REG']}) for mode in ['teams','players']}
            path.write_text(json.dumps(expected))
            subprocess.run(['node','tests/test_data_worker.cjs',str(root/f'data/{season}.json.gz'),str(path),str(root/f'data/lines-{season}.json'),str(root/f'data/advanced-{season}.json.gz')],check=True)
            for typ,low,high in [('REG',2,3),('POST',1,22),('ALL',1,22)]:
                expected={mode:server.aggregate({'season':[str(season)],'mode':[mode],'weekStart':[str(low)],'weekEnd':[str(high)],'seasonType':[typ]}) for mode in ['teams','players']}
                path.write_text(json.dumps(expected))
                subprocess.run(['node','tests/test_data_worker.cjs',str(root/f'data/{season}.json.gz'),str(path),str(root/f'data/lines-{season}.json'),str(root/f'data/advanced-{season}.json.gz'),str(low),str(high),typ],check=True)

if __name__=='__main__': unittest.main()
