import unittest
from types import SimpleNamespace
from unittest.mock import patch
from modules import watchlist as w

class Response:
    def __init__(self, rows): self.rows=rows
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    def raise_for_status(self): pass
    async def json(self): return {'MediaContainer':{'Metadata':self.rows}}

class StateTests(unittest.IsolatedAsyncioTestCase):
    async def test_external_ids_for_movies_and_shows_and_reject_title_only(self):
        for kind in ('movie','show'):
            row={'guid':'plex://'+kind+'/abc','title':'Same title','type':kind,'Guid':[{'id':'imdb://tt123'}]}
            calls=[]
            class Session:
                async def __aenter__(self): return self
                async def __aexit__(self,*args): pass
                def get(self,url,params=None,**kwargs):
                    calls.append((url,params))
                    if '/metadata/' in url:
                        return Response([{'ratingKey':key,'type':kind,'Guid':[{'id':'imdb://tt123' if key=='1' else 'imdb://tt999'}], 'viewOffset':500,'duration':1000,'leafCount':10,'viewedLeafCount':3} for key in url.rsplit('/',1)[-1].split(',')])
                    return Response([] if 'guid' in params else [{'ratingKey':'1'},{'ratingKey':'2'}])
            with patch.object(w,'connect_to_plex',return_value=object()), patch.object(w,'server_for_user',return_value=SimpleNamespace(_baseurl='http://plex',_token='selected')) as select, patch.object(w.aiohttp,'ClientSession',return_value=Session()) as session:
                result=(await w._enrich_items([row],username='Eric'))[0]
                self.assertTrue(result['available_on_server'])
                self.assertEqual([x['media_id'] for x in result['library_items']],['1'])
                self.assertEqual(session.call_args.kwargs['headers']['X-Plex-Token'],'selected')
                self.assertEqual(select.call_args.kwargs['username'],'Eric')
                state=result['library_items'][0]
                self.assertEqual(state['progress_percent'] if kind=='movie' else state['watched_episode_count'],50.0 if kind=='movie' else 3)

    async def test_unmatched_item_only_uses_targeted_searches(self):
        row={'guid':'plex://movie/abc', 'title':'Absent movie', 'type':'movie',
             'Guid':[{'id':'imdb://tt123'}]}
        calls=[]
        class Session:
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            def get(self,url,params=None,**kwargs):
                calls.append((url,params))
                return Response([])
        with patch.object(w,'connect_to_plex',return_value=object()), patch.object(
            w,'server_for_user',return_value=SimpleNamespace(_baseurl='http://plex',_token='selected')
        ), patch.object(w.aiohttp,'ClientSession',return_value=Session()):
            result=(await w._enrich_items([row]))[0]
        self.assertEqual(result['match_status'],'not_found')
        self.assertIsNone(result['available_on_server'])
        self.assertEqual(result['library_items'],[])
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][1]['guid'],row['guid'])
        self.assertEqual(calls[1][1]['title'],row['title'])
        self.assertTrue(all(url.endswith('/library/all') for url,params in calls))

    async def test_failure_preserves_entry_and_unknown_state(self):
        with patch.object(w,'connect_to_plex',side_effect=ValueError('secret')):
            result=(await w._enrich_items([{'title':'Example'}]))[0]
            self.assertEqual(result['title'],'Example')
            self.assertIsNone(result['available_on_server'])
            self.assertNotIn('secret',str(result))
