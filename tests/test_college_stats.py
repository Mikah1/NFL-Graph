import unittest
from college_stats import prepare
from advanced_stats import merge_advanced

class CollegeTests(unittest.TestCase):
 def test_worker_league_cache_isolation(self):
  import subprocess
  subprocess.run(['node','tests/test_college_worker.cjs'],check=True)
 def test_weighted_season_and_postseason(self):
  feeds={k:[] for k in ['teams','schedules','player_box','adv_team','adv_passing','adv_rushing','adv_receiving','adv_defensive']}
  feeds['teams']=[{'team_id':'1','display_name':'School One','conference_short_name':'SEC','team_logo':'school.png'}]
  for game,week,typ,c,a,y in [('g1',1,'2',1,2,20),('g2',2,'2',8,10,80),('bowl',1,'3',1,1,99)]:
   feeds['schedules'].append({'game_id':game,'status':'STATUS_FINAL','season_type':typ,'week':str(week),'home_id':'1','away_id':'2'})
   feeds['player_box'].append({'game_id':game,'team_id':'1','athlete_id':'7','athlete_name':'Full Player Name','category':'passing','stat_1':f'{c}/{a}','stat_2':str(y),'stat_4':'1','stat_5':'0'})
  source=prepare(2026,feeds)
  base={'rows':[],'stats':[],'sources':[]}
  result=merge_advanced(base,source['advanced'],{'mode':['players'],'weekStart':['1'],'weekEnd':['22'],'seasonType':['REG']})
  r=result['rows'][0];self.assertEqual(r['name'],'Full Player Name');self.assertEqual(r['short'],'FPN');self.assertEqual(r['logo'],'school.png')
  self.assertEqual(r['stats']['attempts'],12);self.assertEqual(r['stats']['games'],2);self.assertEqual(r['stats']['completion_pct'],75);self.assertAlmostEqual(r['stats']['yards_per_attempt'],100/12,places=3)
  self.assertIn('completion_pct',result['stats'])
  post=merge_advanced(base,source['advanced'],{'mode':['players'],'weekStart':['1'],'weekEnd':['22'],'seasonType':['POST']})
  self.assertEqual(post['rows'][0]['stats']['passing_yards'],99)
