"""Score, plain-language findings, "what changed", the five tabs, and the HTML file."""
import datetime
import json
import os
from collections import defaultdict

from .checklist import Evaluator
from .checks import CATEGORIES, WHERE_CAP, Checks, where

PRI_W = {'P1': 3, 'P2': 2, 'P3': 1}
HTML_ROWS_PER_ISSUE = 300     # the workbook keeps every row
HTML_PAGES_INTERNAL = 3000    # internal links tab: pages shown in the HTML
HTML_LINKS_PER_PAGE = 100


def score(groups, base):
    """Each check has a weight from its priority (P1=3, P2=2, P3=1).
    An open check costs weight x (0.25 + 0.75 x share of indexable pages affected).
    Checks that could not run are left out of both sides."""
    tot = pen = 0.0
    cats = {k: {'tot': 0.0, 'pen': 0.0, 'open': 0, 'checks': 0} for k in CATEGORIES}
    for g in groups:
        if g['status'] == 'skip':
            continue
        w = PRI_W[g['pri']]
        p = 0.0
        if g['status'] == 'open':
            share = min(1.0, g['aff'] / base) if base else 1.0
            p = w * (0.25 + 0.75 * share)
        g['penalty'] = round(p, 3)
        tot += w
        pen += p
        c = cats[g['cat']]
        c['tot'] += w
        c['pen'] += p
        c['checks'] += 1
        c['open'] += g['status'] == 'open'
    total = round(100 * (1 - pen / tot)) if tot else None
    cat_scores = [{'cat': k, 'score': round(100 * (1 - v['pen'] / v['tot'])), 'open': v['open'], 'checks': v['checks']}
                  for k, v in cats.items() if v['checks']]
    return total, cat_scores


def verdict(s):
    if s is None:
        return 'Not enough data'
    return 'Healthy' if s >= 85 else 'Needs work' if s >= 65 else 'Serious problems'


def analyse(crawl, previous=None):
    groups = Checks(crawl).run()
    base = max(1, len(crawl.indexable))
    total, cats = score(groups, base)
    return {'groups': groups, 'score': total, 'cats': cats}


def findings(crawl, res):
    c = crawl
    out = [f'The crawl found {len(c.pages):,} URLs. {len(c.html):,} are HTML pages on the site, {len(c.live):,} of them load (200) '
           f'and {len(c.indexable):,} can be indexed.']
    open_ = sorted([g for g in res['groups'] if g['status'] == 'open'], key=lambda g: (g['pri'], -g.get('penalty', 0)))
    for g in open_[:7]:
        out.append(g['summary'])
    passed = sum(1 for g in res['groups'] if g['status'] == 'pass')
    out.append(f'{passed} of {sum(1 for g in res["groups"] if g["status"] != "skip")} checks passed with nothing to fix.')
    skipped = [g for g in res['groups'] if g['status'] == 'skip']
    if skipped:
        out.append(f'{len(skipped)} checks did not run because the export is missing a file or column. They are shown as "Not checked" and left out of the score.')
    return out


def changes(now, before):
    """Row-level comparison by the first cell of each row."""
    prev = {g['id']: g for g in before['groups']}
    out = []
    for g in now['groups']:
        p = prev.get(g['id'])
        if not p or g['status'] == 'skip' or p['status'] == 'skip':
            continue
        a = {str(r['c'][0]) for r in p['rows']}
        b = {str(r['c'][0]) for r in g['rows']}
        if a != b:
            out.append({'id': g['id'], 'title': g['title'], 'before': len(a), 'now': len(b), 'fixed': len(a - b), 'new': len(b - a)})
    out.sort(key=lambda x: -(x['fixed'] + x['new']))
    return out


def internal_tab(crawl, cap_pages=None, cap_links=None):
    c = crawl
    pages = []
    for r in sorted(c.indexable, key=lambda r: -len(c.inl.get(r['Address'], []))):
        ls = [l for l in c.inl.get(r['Address'], []) if l.type == 'Hyperlink' and l.src != r['Address'] and l.src in c.pages]
        w, wn = where(ls, cap_links or 10 ** 9)
        pages.append({'u': r['Address'], 'n': len({l.src for l in ls}), 'w': w, 'wn': wn, 't': r.get('Title 1', '')})
    return pages[:cap_pages] if cap_pages else pages


def broken_tab(groups):
    rows = []
    for g in groups:
        if g['id'] not in ('broken', 'broken-res') or g['status'] != 'open':
            continue
        for r in g['rows']:
            for s, a, p, n in r.get('w', []):
                rows.append({'d': r['c'][0], 'st': r['c'][1], 'src': s, 'a': a, 'p': p, 'n': n, 'fix': r['fix'],
                             'k': 'Link' if g['id'] == 'broken' else r['c'][2]})
    return rows


def external_tab(crawl, cap=50):
    c = crawl
    g = defaultdict(list)
    for l in c.links:
        if l.type == 'Hyperlink' and l.dst.startswith('http') and not c.own(l.dst) and l.src in c.pages:
            g[l.dst].append(l)
    out = []
    for d, ls in sorted(g.items(), key=lambda kv: -len({l.src for l in kv[1]})):
        w, wn = where(ls, cap)
        out.append({'u': d, 'st': c.status.get(d) or ls[0].status or '?', 'n': len({l.src for l in ls}), 'w': w, 'wn': wn})
    return out


def build(crawl, res, prev_res=None, prev_name='', crawl_name='', checklist=None):
    groups = res['groups']
    html_groups = []
    for g in groups:
        h = dict(g)
        h['total_rows'] = len(g['rows'])
        h['rows'] = [dict(r, w=r['w'][:WHERE_CAP]) if r.get('w') else r for r in g['rows'][:HTML_ROWS_PER_ISSUE]]
        html_groups.append(h)
    data = {
        'site': crawl.site, 'host': crawl.host,
        'date': datetime.date.today().isoformat(),
        'crawl': crawl_name, 'previous': prev_name,
        'score': res['score'], 'verdict': verdict(res['score']), 'cats': res['cats'],
        'prev_score': prev_res['score'] if prev_res else None,
        'stats': {'urls': len(crawl.pages), 'html': len(crawl.html), 'live': len(crawl.live), 'indexable': len(crawl.indexable),
                  'links': sum(1 for l in crawl.links if l.type == 'Hyperlink'),
                  'sitemap': len(crawl.sitemap_urls) if crawl.sitemap_urls is not None else None},
        'findings': findings(crawl, res),
        'changes': changes(res, prev_res) if prev_res else None,
        'groups': html_groups,
        'checklist': checklist,
        'internal': internal_tab(crawl, HTML_PAGES_INTERNAL, HTML_LINKS_PER_PAGE),
        'internal_total': len(crawl.indexable),
        'broken': [dict(b) for b in broken_tab(groups)][:20000],
        'have_links': crawl.have['inlinks'],
        'external': external_tab(crawl),
        'where_cap': WHERE_CAP,
    }
    return data


def write_html(data, path):
    tpl = open(os.path.join(os.path.dirname(__file__), 'template.html'), encoding='utf-8').read()
    blob = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    title = f'SEO audit: {data["host"]}'
    html = tpl.replace('%%TITLE%%', title).replace('%%DATA%%', blob)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)


def run_checklist(crawl, res, has_previous):
    return Evaluator(crawl, res['groups'], has_previous).run()
