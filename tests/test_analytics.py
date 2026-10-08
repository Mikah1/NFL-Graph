import unittest
import server

class AnalyticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=server.load(2026)

    def test_team_totals_and_denominators(self):
        d=server.aggregate({'season':['2026'],'mode':['teams']})
        self.assertEqual(len(d['rows']),32)
        self.assertEqual(sum(r['stats']['off_plays'] for r in d['rows']),d['plays'])
        self.assertEqual(sum(r['stats']['def_plays'] for r in d['rows']),d['plays'])
        for r in d['rows']:
            s=r['stats']
            self.assertAlmostEqual(s['off_epa_per_play'],s['off_epa_total']/s['off_plays'],places=3)
            self.assertGreaterEqual(s['off_success_rate'],0)
            self.assertLessEqual(s['off_success_rate'],100)

    def test_week_filter_and_player_rates(self):
        d=server.aggregate({'season':['2026'],'mode':['players'],'weekStart':['1'],'weekEnd':['1']})
        self.assertTrue(d['rows'])
        for r in d['rows']:
            self.assertEqual(r['stats']['games'],1)
            s=r['stats']
            if s.get('attempts'):
                self.assertAlmostEqual(s['completion_pct'],100*s['completions']/s['attempts'],places=3)

    def test_unavailable_postseason_is_empty(self):
        d=server.aggregate({'season':['2026'],'seasonType':['POST']})
        self.assertEqual(d['rows'],[])
        self.assertEqual(d['plays'],0)

    def test_view_switch_reuses_computed_slice(self):
        from unittest.mock import patch
        query={'season':['2026'],'weekStart':['1'],'weekEnd':['2'],'includeLines':['0']}
        server.aggregate({**query,'mode':['teams']})
        with patch.object(server,'number',side_effect=AssertionError('stats should not be recalculated')):
            players=server.aggregate({**query,'mode':['players']})
            self.assertTrue(players['rows'])
            self.assertIs(players,server.aggregate({**query,'mode':['players']}))

    def test_stale_disk_cache_does_not_wait_for_network(self):
        from unittest.mock import patch
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import os, time
        with TemporaryDirectory() as folder:
            path=Path(folder)/'old.csv'
            path.write_text('cached data')
            old=time.time()-30000
            os.utime(path,(old,old))
            with patch.object(server,'CACHE',Path(folder)),patch.object(server.threading.Thread,'start') as start,patch.object(server.urllib.request,'urlopen') as network:
                self.assertEqual(server.fetch('old.csv','https://example.com/data'),path)
                network.assert_not_called()
                start.assert_called_once()
            server.refresh_jobs.discard('old.csv')

    def test_invalid_season(self):
        with self.assertRaises(ValueError): server.aggregate({'season':['1990']})

if __name__=='__main__': unittest.main()
