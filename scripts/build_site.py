#!/usr/bin/env python3
"""Update current-season website sections from validated ESPN snapshot. Historical content untouched."""
import json, sys, argparse, html
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
from bs4 import BeautifulSoup

MANAGERS={1:'Jack Pendergast',3:'Oli Cooke',4:'Tom Gatenby',6:'Jared Butler',7:'Oliver Hayes',8:'Bonner Youngblood',9:'Jake Knowlton-Parry',10:'Taylor Wells',11:'Jason Roberts',12:'William Leonard'}

def build(snapshot, template, ledger="data/chug_status.json", player_points="data/player_points_2026.json", image_dir="images/chugs"):
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
    # Player Lab: never present 2025 statistics as 2026 season points.
    lab=soup.find('section',id='playerlab')
    if lab:
        current=lab.find('details',attrs={'data-season':'2026'})
        if current:
            payload={}
            if Path(player_points).exists():
                payload=json.loads(Path(player_points).read_text(encoding='utf-8'))
                if int(payload.get('season',0))!=2026:raise ValueError('Wrong player points season')
            points=payload.get('points_by_name',{})
            rows=current.select('tbody tr')
            for tr in rows:
                cells=tr.find_all('td')
                if len(cells)<5:continue
                name=cells[1].get_text(' ',strip=True)
                cells[4].string=f"{points[name]:.2f}" if name in points else '—'
            rows.sort(key=lambda tr:-(float(tr.find_all('td')[4].get_text()) if tr.find_all('td')[4].get_text()!='—' else -1))
            tbody=current.find('tbody');tbody.clear()
            for tr in rows:tbody.append(tr)
            if current.find('summary'):
                current.find('summary').string='2026 Draft Scoring · available season-to-date totals'
            caution=lab.find(class_='archive-caution')
            if caution:
                if payload:
                    caution.string=f"2026 fantasy points: ESPN 2026 player export through Week {payload.get('through_week','?')} (not updated by Tuesday matchup refresh). Dashes mean no verified 2026 total in the export. Prior seasons retain their archived figures."
                else:
                    caution.string='2026 fantasy point totals unavailable until verified 2026 player data is supplied. Prior seasons retain their archived figures.'
    # Highlight lowest scorer from the latest fully completed regular-season week.
    all_week_scores={}
    for m in complete:
        w=int(m['week'])
        all_week_scores.setdefault(w,[]).extend([(int(m['home_id']),float(m['home_points'])),(int(m['away_id']),float(m['away_points']))])
    for w,scores in all_week_scores.items():
        if len(scores)!=10 or len({i for i,_ in scores})!=10:raise ValueError(f'Incomplete chug scoreboard week {w}')
    ledger_path=Path(ledger)
    status=json.loads(ledger_path.read_text(encoding='utf-8')) if ledger_path.exists() else {}
    status=status.get('2026',{})
    valid={'paid','unpaid','unverified'}
    if any(v not in valid for v in status.values()):raise ValueError('Invalid chug ledger status')
    last_scores=sorted(all_week_scores[last],key=lambda t:t[1]);loser_id,loser_points=last_scores[0]
    chug=soup.new_tag('section',id='chug-tracker')
    tag=soup.new_tag('div',attrs={'class':'tag'});tag.string=f'Week {last} · Lowest score pays';chug.append(tag)
    h2=soup.new_tag('h2');h2.string='🍺 The Chug Watch';chug.append(h2)
    intro=soup.new_tag('p',attrs={'class':'chug-lede'});intro.string=f'{MANAGERS[loser_id]} · {loser_points:.2f} points · Thursday deadline';chug.append(intro)
    hint=soup.new_tag('p',attrs={'class':'small'});hint.string='Final weekly scores, lowest to highest. Chug completion is tracked separately from ESPN.';chug.append(hint)
    bars=soup.new_tag('div',attrs={'class':'chug-bars'})
    top_score=max(v for _,v in last_scores) or 1
    for idx,(i,pts) in enumerate(last_scores):
        item=soup.new_tag('div',attrs={'class':'chug-bar-row'+(' chug-lowest' if idx==0 else '')})
        name=soup.new_tag('span',attrs={'class':'chug-name'});name.string=MANAGERS[i];item.append(name)
        track=soup.new_tag('div',attrs={'class':'chug-track'});fillbar=soup.new_tag('div',attrs={'class':'chug-fill'});fillbar['style']=f'width:{max(2,100*pts/top_score):.1f}%';track.append(fillbar);item.append(track)
        value=soup.new_tag('strong');value.string=f'{pts:.2f}';item.append(value);bars.append(item)
    chug.append(bars)
    debt=soup.new_tag('h3');debt.string='2026 Chug Ledger';chug.append(debt)
    table=soup.new_tag('table',attrs={'class':'chug-ledger'})
    thead=soup.new_tag('thead');tr=soup.new_tag('tr')
    for label in ('Week','Lowest scorer','Points','Status'):
        th=soup.new_tag('th');th.string=label;tr.append(th)
    thead.append(tr);table.append(thead);tbody=soup.new_tag('tbody')
    for w in sorted(all_week_scores,reverse=True):
        i,pts=min(all_week_scores[w],key=lambda t:t[1]);state=status.get(str(w),'paid' if w<=5 else 'unverified')
        tr=soup.new_tag('tr')
        for val in (str(w),MANAGERS[i],f'{pts:.2f}',state.upper()):
            td=soup.new_tag('td');td.string=val
            if val==state.upper():td['class']='chug-status-'+state
            tr.append(td)
        tbody.append(tr)
    table.append(tbody);wrap=soup.new_tag('div',attrs={'class':'scroll'});wrap.append(table);chug.append(wrap)
    note=soup.new_tag('p',attrs={'class':'small'});note.string='Commissioner updates payment status in data/chug_status.json; ESPN updates never overwrite it.';chug.append(note)
    weekly.insert_before(chug)
    nav=soup.find('nav')
    if nav:
        a=soup.new_tag('a',href='#chug-tracker');a.string='🍺 Chug Watch';nav.insert(1,a)
        gallery_link=nav.find('a',href='#gallery')
        if gallery_link:gallery_link.string='🍻 Chug Photos'
    css=soup.new_tag('style');css.string="""
    #chug-tracker{max-width:1160px;margin:30px auto 0;padding:0 20px;scroll-margin-top:85px}
    .chug-lede{font:700 clamp(20px,3vw,30px) Georgia,serif;margin:8px 0;color:#9b452d}
    .chug-bars{background:#fffefa;border:1px solid #d7dcd0;border-radius:12px;padding:15px;margin:15px 0 25px}
    .chug-bar-row{display:grid;grid-template-columns:minmax(125px,210px) minmax(80px,1fr) 65px;align-items:center;gap:12px;padding:8px;border-radius:6px}
    .chug-bar-row strong{text-align:right;font-variant-numeric:tabular-nums}
    .chug-name{font-weight:650;font-size:13px}.chug-track{height:17px;background:#e8ece4;border-radius:5px;overflow:hidden}
    .chug-fill{height:100%;background:#507b5e;border-radius:5px}.chug-lowest{background:#f9e8dd}.chug-lowest .chug-fill{background:#b95c3f}
    .chug-ledger{min-width:420px}.chug-status-unpaid{font-weight:900;color:#a83d26}.chug-status-paid{font-weight:800;color:#276b46}.chug-status-unverified{font-weight:700;color:#796f54}
    @media(max-width:600px){.chug-bar-row{grid-template-columns:110px minmax(50px,1fr) 55px;gap:6px;padding:8px 3px}.chug-name{font-size:11px}.chug-bar-row strong{font-size:11px}}
    """;soup.head.append(css)
    # Future photo uploads: add files under images/chugs/; no base64 conversion required.
    gallery=soup.find('section',id='gallery')
    folder=Path(image_dir)
    if gallery and folder.exists():
        grid=gallery.find(class_='photo-grid')
        if grid:
            for f in sorted(folder.iterdir()):
                if f.is_file() and f.suffix.lower() in ('.jpg','.jpeg','.png','.webp'):
                    figure=soup.new_tag('figure',attrs={'class':'photo-tile'})
                    img=soup.new_tag('img',src=f'{folder.as_posix()}/{f.name}',loading='lazy',alt=f'Chug archive photo {f.stem}')
                    figure.append(img);caption=soup.new_tag('figcaption');caption.string=f.stem.replace('_',' ').replace('-',' ');figure.append(caption);grid.append(figure)
    return str(soup)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot',default='espn-preview.json');p.add_argument('--template',default='site-template.html');p.add_argument('--output',default='index.html');p.add_argument('--ledger',default='data/chug_status.json');p.add_argument('--player-points',default='data/player_points_2026.json');p.add_argument('--image-dir',default='images/chugs');a=p.parse_args()
    try:
        html=build(a.snapshot,a.template,a.ledger,a.player_points,a.image_dir)
        Path(a.output).write_text(html,encoding='utf-8')
        print('Validated and built',a.output,'from',a.snapshot)
    except Exception as e:
        print('SAFE STOP: Website NOT updated:',e,file=sys.stderr);sys.exit(1)
