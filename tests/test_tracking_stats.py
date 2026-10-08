import unittest
from tracking_stats import prepare
from advanced_stats import merge_advanced
class TrackingTests(unittest.TestCase):
 def data(self):
  raw={'teams':{},'players':[{'player_id':'qb','player_display_name':'QB','position':'QB'}],'plays':[]}
  def row(week,n,time,distance):return {'season':'2026','week':str(week),'season_type':'REG','player_gsis_id':'qb','team_abbr':'KC','player_display_name':'QB','player_position':'QB','attempts':str(n),'completions':str(n),'avg_time_to_throw':str(time),'max_completed_air_distance':str(distance),'avg_completed_air_yards':'5','avg_intended_air_yards':'8'}
  return prepare(2026,raw,{'passing':[row(0,1000,100,999),row(1,10,2,30),row(2,30,4,50)]},1)
 def test_week_zero_excluded_weighting_and_maximum(self):
  d=self.data();r=merge_advanced({'rows':[],'stats':[],'sources':[]},d,{'mode':['players']},'trackingCoverage');s=r['rows'][0]['stats']
  self.assertEqual(s['ngs_passing_time_to_throw'],3.5)
  self.assertEqual(s['ngs_passing_max_completed_air_distance'],50)
  self.assertEqual(s['ngs_passing_air_yards_differential'],-3)
  self.assertEqual(r['rows'][0]['advancedSamples']['ngs_passing_sample'],40)
  one=merge_advanced({'rows':[],'stats':[],'sources':[]},d,{'mode':['players'],'weekEnd':['1']});self.assertEqual(one['rows'][0]['stats']['ngs_passing_time_to_throw'],2)
 def test_supplements_preserve_previous_samples_and_stats(self):
  base={'rows':[{'id':'qb','stats':{'passing_yards':100},'advancedSamples':{'pass_attempts':99}}],'stats':['passing_yards'],'sources':[]}
  r=merge_advanced(base,self.data(),{'mode':['players']},'trackingCoverage')
  self.assertEqual(r['rows'][0]['advancedSamples']['pass_attempts'],99)
  self.assertEqual(r['rows'][0]['stats']['passing_yards'],100)
  self.assertEqual(base['rows'][0]['stats'],{'passing_yards':100})
 def test_scrambles_are_counted_as_qb_dropbacks(self):
  p={'game_id':'g','week':'1','season_type':'REG','posteam':'KC','defteam':'BUF','play_type':'run','qb_dropback':'1','qb_scramble':'1','rusher_player_id':'qb','rusher_player_name':'QB','qb_epa':'2','wpa':'.1','down':'3','yardline_100':'10','epa':'2','third_down_converted':'1'}
  d=prepare(2026,{'teams':{},'players':[],'plays':[p]}, {},1)
  r=merge_advanced({'rows':[],'stats':[],'sources':[]},d,{'mode':['players']})
  self.assertEqual(r['rows'][0]['stats']['passing_qb_epa_per_dropback'],2)
  self.assertEqual(r['rows'][0]['stats']['rushing_scrambles'],1)
  t=merge_advanced({'rows':[],'stats':[],'sources':[]},d,{'mode':['teams']})
  kc=next(r for r in t['rows'] if r['id']=='KC');self.assertEqual(kc['stats']['off_3down_conversion_pct'],100)

 def test_super_bowl_calendar_week_aligns_with_nflverse(self):
  r={'season':'2025','week':'23','season_type':'POST','player_gsis_id':'q','team_abbr':'KC','player_display_name':'QB','player_position':'QB','attempts':'10','avg_time_to_throw':'2'}
  d=prepare(2025,{'teams':{},'players':[],'plays':[]},{'passing':[r]},1)
  self.assertEqual(d['slices'][0]['week'],22)
