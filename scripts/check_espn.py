#!/usr/bin/env python3
"""Fetch public ESPN league data and validate a non-publishing weekly snapshot."""
import json, os, sys, urllib.request, datetime
from pathlib import Path
LEAGUE = '1631713270'
SEASON = 2026
BASE = f'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}/segments/0/leagues/{LEAGUE}'

def fetch(view):
    req=urllib.request.Request(BASE+'?view='+view, headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data=json.load(r)
    if str(data.get('id')) != LEAGUE or int(data.get('seasonId',0)) != SEASON:
        raise ValueError(f'Unexpected ESPN league/season for {view}')
    return data

def main():
    teams=fetch('mTeam')
    matchups=fetch('mMatchup')
    current=int(matchups.get('status',{}).get('currentMatchupPeriod',0))
    all_teams=teams.get('teams',[])
    schedule=matchups.get('schedule',[])
    if len(all_teams)!=10 or not schedule or current<1:
        raise ValueError(f'Unexpected league data: teams={len(all_teams)} schedule={len(schedule)} current={current}')
    ids={int(t['id']) for t in all_teams}
    games=[]
    for m in schedule:
        period=int(m.get('matchupPeriodId',0))
        if period > current or period < 1: continue
        h=m.get('home',{}); a=m.get('away',{})
        if not h or not a: continue
        if int(h.get('teamId',-1)) not in ids or int(a.get('teamId',-1)) not in ids: raise ValueError('Unknown team in matchup')
        games.append({'week':period,'home_id':h['teamId'],'away_id':a['teamId'],
                      'home_points':h.get('totalPoints'),'away_points':a.get('totalPoints'),
                      'winner':m.get('winner','UNDECIDED'),'tier':m.get('playoffTierType','NONE')})
    if not games: raise ValueError('No matchup data')
    # ESPN can return partial live scores. Only finalized periods prior to current are candidates.
    completed=[g for g in games if g['week']<current and g['winner'] in ('HOME','AWAY','TIE')]
    if not completed: raise ValueError('No completed matchups; refusing to report scores')
    snapshot={'league_id':LEAGUE,'season':SEASON,'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'current_matchup_period':current,'team_count':len(all_teams),'matchup_count':len(games),
              'completed_matchup_count':len(completed),'teams':[{'id':t['id'],'name':t.get('name','')} for t in all_teams],
              'completed_matchups':completed,'current_matchups':[g for g in games if g['week']==current]}
    Path('espn-preview.json').write_text(json.dumps(snapshot,indent=2)+'\n',encoding='utf-8')
    print(f"Validated league {LEAGUE}: {len(all_teams)} teams, {len(completed)} completed matchups, current week {current}.")
    print('Created espn-preview.json. No website files changed or published.')
if __name__=='__main__':
    try: main()
    except Exception as e:
        print(f'ESPN validation failed: {e}',file=sys.stderr);sys.exit(1)
