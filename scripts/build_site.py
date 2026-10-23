#!/usr/bin/env python3
"""Update current-season website sections from validated ESPN snapshot. Historical content untouched."""
import json, sys, argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
from bs4 import BeautifulSoup

MANAGERS={1:'Jack Pendergast',3:'Oli Cooke',4:'Tom Gatenby',6:'Jared Butler',7:'Oliver Hayes',8:'Bonner Youngblood',9:'Jake Knowlton-Parry',10:'Taylor Wells',11:'Jason Roberts',12:'William Leonard'}

def build(snapshot, template):
    d=json.loads(Path(snapshot).read_text(encoding='utf-8'))
    assert str(d['league_id'])=='1631713270' and int(d['season'])==2026
    teams={int(t['id']):t['name'].strip() for t in d['teams']}
    assert set(teams)==set(MANAGERS), 'Team IDs changed; manual review required'
    week=int(d['current_matchup_period'])
    assert 2<=week<=18, 'Unexpected current week'
    complete=[m for m in d['completed_matchups'] if int(m['week'])<week and m['winner'] in ('HOME','AWAY','TIE') and m.get('tier','NONE')=='NONE']
    regular_weeks=sorted(set(int(m['week']) for m in complete))
    assert regular_weeks and len(complete)==len(regular_weeks)*5, 'Missing/duplicate regular season matchups; refusing to publish'
    assert all(sum(int(m['week'])==w for m in complete)==5 for w in regular_weeks)
    assert len({(m['week'], min(m['home_id'],m['away_id']), max(m['home_id'],m['away_id'])) for m in complete})==len(complete)
    stats={i:dict(w=0,l=0,t=0,pf=0.0,played=0) for i in teams}
    for m in complete:
        h,a=int(m['home_id']),int(m['away_id']); hp,ap=m['home_points'],m['away_points']
        assert isinstance(hp,(float,int)) and isinstance(ap,(float,int)) and 0<=hp<400 and 0<=ap<400
        for i,p in [(h,hp),(a,ap)]:stats[i]['pf']+=p;stats[i]['played']+=1
        if m['winner']=='HOME':stats[h]['w']+=1;stats[a]['l']+=1
        elif m['winner']=='AWAY':stats[a]['w']+=1;stats[h]['l']+=1
        else:stats[h]['t']+=1;stats[a]['t']+=1
    assert all(s['played']==len(regular_weeks) for s in stats.values()),'Uneven completed weeks; review required'
    # Standings sorted by wins, then points for; not claiming official ESPN tiebreaks.
    order=sorted(teams,key=lambda i:(-stats[i]['w'],-stats[i]['t'],-stats[i]['pf']))
    # Transparent power ranking: points per game, with wins as tiebreaker.
    power=sorted(teams,key=lambda i:(-stats[i]['pf']/stats[i]['played'],-stats[i]['w']))
    soup=BeautifulSoup(Path(template).read_text(encoding='utf-8'),'html.parser')
    def table_body(section):return soup.find('section',id=section).find('tbody')
    def fill(tb,rows):
        tb.clear()
        for cells in rows:
            tr=soup.new_tag('tr')
            for value in cells:
                td=soup.new_tag('td');td.string=str(value);tr.append(td)
            tb.append(tr)
    def record(i):
        s=stats[i];return f"{s['w']}–{s['l']}"+(f"–{s['t']}" if s['t'] else '')
    fill(table_body('standings'),[[n,MANAGERS[i],teams[i],record(i),f"{stats[i]['pf']:.2f}"] for n,i in enumerate(order,1)])
    fill(table_body('power'),[[f'#{n}',MANAGERS[i],record(i),f"{stats[i]['pf']/stats[i]['played']:.2f}"] for n,i in enumerate(power,1)])
    pw=soup.find('section',id='power');pw.find(class_='tag').string=f"2026 · Through Week {max(regular_weeks)} · Ranked by points per game"
    weekly=soup.find('section',id='weekly')
    weekly.find(class_='tag').string='ESPN snapshot · '+datetime.fromisoformat(d['checked_utc'].replace('Z','+00:00')).strftime('%B %d, %Y')
    weekly.find('h2').string=f'Week {week} Matchups'
    cards=weekly.find(class_='grid')
    cards.clear()
    upcoming=[m for m in d['current_matchups'] if m.get('tier','NONE')=='NONE']
    if len(upcoming)!=5:raise ValueError('Expected five current-week matchups')
    for m in upcoming:
        h,a=int(m['home_id']),int(m['away_id'])
        card=soup.new_tag('div',attrs={'class':'card'});h3=soup.new_tag('h3')
        for j,name in enumerate([MANAGERS[a],'VS',MANAGERS[h]]):
            span=soup.new_tag('span',attrs={'class':'matchup-vs' if j==1 else 'matchup-team'});span.string=name;h3.append(span)
        card.append(h3);meta=soup.new_tag('div',attrs={'class':'matchup-meta'})
        meta.string=f"{record(a)} · {stats[a]['pf']/stats[a]['played']:.2f} PPG     |     {record(h)} · {stats[h]['pf']/stats[h]['played']:.2f} PPG";card.append(meta);cards.append(card)
    last=max(regular_weeks)
    h2s=weekly.find_all('h2');h2s[1].string=f'Week {last}: The Scoreboard'
    grid=weekly.find_all(class_='grid')[1];grid.clear()
    games=[m for m in complete if int(m['week'])==last]
    top=max([(p,i) for m in games for i,p in [(int(m['home_id']),m['home_points']),(int(m['away_id']),m['away_points'])]])
    closest=min(games,key=lambda m:abs(m['home_points']-m['away_points']))
    widest=max(games,key=lambda m:abs(m['home_points']-m['away_points']))
    def winner(m):return int(m['home_id'] if m['winner']=='HOME' else m['away_id']) if m['winner']!='TIE' else None
    for label,headline,description in [
        ('Top score',f'{MANAGERS[top[1]]} drops {top[0]:.2f}',f'Highest score in Week {last}'),
        ('Nail-biter',f"{abs(closest['home_points']-closest['away_points']):.2f}-point margin",f"{MANAGERS[int(closest['home_id'])]} vs. {MANAGERS[int(closest['away_id'])]}"),
        ('Biggest win',f"{abs(widest['home_points']-widest['away_points']):.2f}-point margin",f"{MANAGERS[winner(widest)]} wins" if winner(widest) else 'Tie')]:
        card=soup.new_tag('div',attrs={'class':'card'})
        for tag,cls,value in [('div','tag',label),('h3',None,headline),('div','small',description)]:
            el=soup.new_tag(tag,attrs={'class':cls} if cls else {});el.string=value;card.append(el)
        grid.append(card)
    fill(weekly.find('tbody'),[[MANAGERS[int(m['away_id'])],f"{m['away_points']:.2f}",MANAGERS[int(m['home_id'])],f"{m['home_points']:.2f}",MANAGERS[winner(m)] if winner(m) else 'Tie'] for m in games])
    # Current-year recap archive is deliberately left untouched: it is an editorial archive, not a live feed.
    # Hide old recap entries once the current week has moved on, avoiding stale 'latest' claims.
    if week>7:
        recaps=soup.find('section',id='recaps')
        if recaps:
            notice=soup.new_tag('p',attrs={'class':'small'});notice.string=f'2026 recap archive below reflects previously published editorial coverage. Current results are in the Week {week} scoreboard above.'
            recaps.insert(1,notice)
    return str(soup)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot',default='espn-preview.json');p.add_argument('--template',default='site-template.html');p.add_argument('--output',default='index.html');a=p.parse_args()
    try:
        html=build(a.snapshot,a.template)
        Path(a.output).write_text(html,encoding='utf-8')
        print('Validated and built',a.output,'from',a.snapshot)
    except Exception as e:
        print('SAFE STOP: Website NOT updated:',e,file=sys.stderr);sys.exit(1)
