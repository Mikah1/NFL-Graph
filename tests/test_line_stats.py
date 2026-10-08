import unittest
from line_stats import merge_snapshot, parse_article

class LineStatsTests(unittest.TestCase):
    def test_merge_joins_identity_preserves_missing_values_and_base(self):
        base={'rows':[{'id':'known','stats':{'def_sacks':2}}],'stats':['def_sacks'],'sources':[]}
        snapshot={'throughWeek':4,'source':{'name':'ESPN'},'players':[{'id':'known','stats':{'line_pass_rush_win_rate':25}}, {'id':'ol','stats':{'line_pass_block_win_rate':94,'line_pass_block_plays':108}}]}
        result=merge_snapshot(base,snapshot,{'mode':['players']})
        self.assertEqual(result['rows'][0]['stats']['def_sacks'],2)
        self.assertEqual(result['rows'][0]['stats']['line_pass_rush_win_rate'],25)
        self.assertNotIn('games',result['rows'][1]['stats'])
        self.assertEqual(base['rows'][0]['stats'],{'def_sacks':2})
        for query in [{'weekStart':['2']},{'weekEnd':['3']},{'seasonType':['POST']}]:
            filtered=merge_snapshot(base,snapshot,{'mode':['players'],**query})
            self.assertFalse(filtered['lineSnapshot']['compatible'])
            self.assertEqual(filtered['rows'],base['rows'])
            self.assertIn('line_pass_block_win_rate',filtered['stats'])

    def test_parser_rejects_wrong_season_and_incomplete_feed(self):
        with self.assertRaises(ValueError):parse_article({'headline':'2025 NFL rankings'},2026,[],lambda _: {})
        with self.assertRaises(ValueError):parse_article({'headline':'2026 NFL rankings','inlines':[]},2026,[],lambda _: {})

    def test_parser_keeps_published_rates_and_roster_identity(self):
        modules=[]
        for group in range(8):
            metric=['PRWR','PBWR','RSWR','RBWR'][group//2]
            body=[[str(i+1),f'<a href="/nfl/player/_/id/{group*10+i+1}/name">Player {i}</a>','T0','1','2','90%','35%'] for i in range(10)]
            modules.append({'headline':'OT leaderboard','json':{'header':['Rank','Name','Team','Wins','Plays',metric,'DT%'],'body':body}})
        modules.append({'json':{'header':['Team','PRWR','RSWR','PBWR','RBWR'],'body':[[f'<a href="/nfl/team/_/name/t{i}/">Team {i}</a>',*['55% (9)']*4] for i in range(32)]}})
        article={'headline':'2026 NFL win rates','story':'Through Week 4 games','lastModified':'2026-10-06T13:19:52Z','inlines':modules}
        snapshot=parse_article(article,2026,[{'espn_id':'1','gsis_id':'joined','position':'DE'}],lambda a:{'team':a,'name':a})
        row=next(r for r in snapshot['players'] if r['id']=='joined')
        self.assertEqual(row['position'],'DE')
        self.assertEqual(row['stats']['line_pass_rush_win_rate'],90)
        self.assertEqual(row['stats']['line_pass_rush_double_team_rate'],35)
        self.assertEqual(snapshot['throughWeek'],4)
        self.assertEqual(snapshot['teams'][0]['stats']['line_pass_block_rank'],9)
