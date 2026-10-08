import unittest
from advanced_stats import prepare,merge_advanced,RATIOS,FIELDS,derive

class AdvancedStatsTests(unittest.TestCase):
    def make_data(self):
        def row(week,carries,before,after,typ='REG',pid='P1'):
            return {'season':'2026','week':str(week),'game_type':typ,'game_id':f'2026_{week}_{typ}','team':'KAN','pfr_player_name':'Runner','pfr_player_id':pid,'carries':str(carries),'rushing_yards_before_contact':str(before),'rushing_yards_after_contact':str(after),'rushing_broken_tackles':'0'}
        first=row(1,2,10,4)
        feeds={'rush':[first,first.copy(),row(2,8,8,20),row(19,1,-1,3,'WC')]}
        identity=[{'pfr_id':'P1','gsis_id':'GSIS','position':'RB'}]
        info=lambda a:{'team':a,'name':a,'conference':'AFC'}
        return prepare(2026,feeds,identity,[],info,123)

    def test_weighted_contact_averages_filters_and_identity(self):
        data=self.make_data();base={'rows':[{'id':'GSIS','stats':{'carries':99,'rushing_yards':100}}],'stats':['carries','rushing_yards'],'sources':[]}
        result=merge_advanced(base,data,{'mode':['players'],'seasonType':['REG']})
        row=result['rows'][0];s=row['stats']
        self.assertEqual(len(result['rows']),1)
        self.assertEqual(s['rushing_yards_before_contact'],18)
        self.assertEqual(s['rushing_yards_after_contact'],24)
        self.assertEqual(s['rushing_yards_before_contact_per_carry'],1.8)
        self.assertEqual(s['rushing_yards_after_contact_per_carry'],2.4)
        self.assertEqual(s['carries'],99)
        self.assertNotIn('rushing_yards_before_contact',base['rows'][0]['stats'])
        weekly=merge_advanced(base,data,{'mode':['players'],'weekStart':['2'],'weekEnd':['2']})
        self.assertEqual(weekly['rows'][0]['stats']['rushing_yards_before_contact_per_carry'],1)
        post=merge_advanced(base,data,{'mode':['players'],'seasonType':['POST']})
        self.assertEqual(post['rows'][0]['stats']['rushing_yards_before_contact'],-1)
        empty=merge_advanced(base,data,{'mode':['players'],'weekStart':['3'],'weekEnd':['4']})
        self.assertNotIn('rushing_yards_after_contact',empty['rows'][0]['stats'])
        self.assertIn('rushing_yards_after_contact',empty['stats'])

    def test_team_totals_use_charted_carries_and_zero_is_not_missing(self):
        data=self.make_data();base={'rows':[],'stats':[],'sources':[]}
        result=merge_advanced(base,data,{'mode':['teams']})
        s=result['rows'][0]['stats']
        self.assertEqual(result['rows'][0]['id'],'KC')
        self.assertEqual(s['rushing_yards_after_contact_per_carry'],2.4)
        self.assertEqual(s['rushing_broken_tackle_rate'],0)
        self.assertIsNone(s['rushing_carries_per_broken_tackle'])
        s={'rushing_yards_after_contact':0};derive(s,{'rush_carries':0})
        self.assertIsNone(s['rushing_yards_after_contact_per_carry'])

    def test_defensive_ratios_and_rating_recompute_from_counts(self):
        stats={'def_targets':10,'def_completions_allowed':5,'def_yards_allowed':50,'def_receiving_tds_allowed':0,'def_missed_tackles':2}
        derive(stats,{'def_interceptions':1,'def_tackle_opportunities':20,'def_target_air_yards':80})
        self.assertEqual(stats['def_completion_pct_allowed'],50)
        self.assertEqual(stats['def_missed_tackle_pct'],10)
        self.assertEqual(stats['def_average_depth_of_target'],8)
        self.assertEqual(stats['def_passer_rating_allowed'],25)

    def test_new_catalog_has_no_existing_box_score_duplicates(self):
        existing={'carries','rushing_yards','rushing_tds','rushing_first_downs','receiving_yards_after_catch','def_sacks','def_qb_hits','def_interceptions','def_tackles_solo','def_sack_yards'}
        keys=set(RATIOS)|{k for fields in FIELDS.values() for k in fields.values()}
        self.assertFalse(keys&existing)
