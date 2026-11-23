"""The .xlsx workbook: the same data as the dashboard, one sheet per view."""
from .report import broken_tab, external_tab, internal_tab

MAX_ROWS = 1_000_000  # Excel stops at 1,048,576 rows per sheet


def write_xlsx(data, res, crawl, path):
    try:
        from openpyxl import Workbook
        from openpyxl.cell import WriteOnlyCell
        from openpyxl.styles import Font, PatternFill
    except ImportError:
        print('openpyxl is not installed, so the .xlsx was skipped. Run: pip install -r requirements.txt')
        return False

    wb = Workbook(write_only=True)
    bold = Font(bold=True, color='FFFFFF')
    fill = PatternFill('solid', fgColor='334155')

    def sheet(name, head, rows, widths=None):
        ws = wb.create_sheet(name)
        if widths:
            for col, w in zip('ABCDEFGHIJKLMNOP', widths):
                ws.column_dimensions[col].width = w
        ws.freeze_panes = 'A2'
        cells = []
        for h in head:
            c = WriteOnlyCell(ws, value=h)
            c.font, c.fill = bold, fill
            cells.append(c)
        ws.append(cells)
        n = 0
        for r in rows:
            if n >= MAX_ROWS:
                ws.append(['(stopped at the Excel row limit)'])
                break
            ws.append([v if not isinstance(v, str) else v[:32000] for v in r])
            n += 1
        return ws

    s = data['stats']
    import re
    sample = [['SAMPLE DATA', 'Built from a made-up crawl of a reserved example domain. None of this data is real.']] if re.search(r'(^|\.)example\.(com|org|net)$|\.example$', data['host']) else []
    summary = sample + [
        ['Site', data['site']], ['Report date', data['date']], ['Crawl folder', data['crawl']],
        ['Health score (out of 100)', data['score']], ['Verdict', data['verdict']],
        ['URLs crawled', s['urls']], ['HTML pages on the site', s['html']], ['Pages that load (200)', s['live']],
        ['Indexable pages', s['indexable']], ['Internal and external hyperlinks', s['links']],
        ['Sitemap URLs', s['sitemap'] if s['sitemap'] is not None else 'no sitemap given'],
    ]
    if data['previous']:
        summary += [['Compared with', data['previous']], ['Previous score', data['prev_score']]]
    summary += [[], ['What the crawl found']] + [['', f] for f in data['findings']]
    summary += [[], ['Category', 'Score', 'Open checks', 'Checks run']] + [[c['cat'], c['score'], c['open'], c['checks']] for c in data['cats']]
    sheet('Summary', ['Item', 'Value'], summary, [34, 110])

    groups = sorted(res['groups'], key=lambda g: ({'open': 0, 'pass': 1, 'skip': 2}[g['status']], g['pri']))
    st_name = {'open': 'Open', 'pass': 'Passed', 'skip': 'Not checked'}
    sheet('Fix list', ['Priority', 'Status', 'Category', 'Issue', 'Owner', 'Items', 'Pages affected', 'What we found', 'Why it matters', 'How to fix', 'Done when'],
          ([g['pri'], st_name[g['status']], g['cat'], g['title'], g['owner'], len(g['rows']), g['aff'], g['summary'], g['why'], _plain(g['fix']), g['done']] for g in groups),
          [8, 12, 22, 44, 12, 8, 10, 50, 50, 60, 50])

    def issue_rows():
        for g in groups:
            if g['status'] != 'open':
                continue
            for r in g['rows']:
                detail = ' | '.join(f'{h}: {v}' for h, v in zip(g['cols'][1:], r['c'][1:]))
                if r.get('w'):
                    for src, a, p, n in r['w']:
                        yield [g['pri'], g['title'], g['owner'], str(r['c'][0]), detail, r['fix'], src, a, p, n]
                else:
                    yield [g['pri'], g['title'], g['owner'], str(r['c'][0]), detail, r['fix'], '', '', '', '']
    sheet('Issue details', ['Priority', 'Issue', 'Owner', 'Affected URL', 'Details', 'Fix', 'Linking page', 'Anchor / alt text', 'Link position', 'Times'],
          issue_rows(), [8, 36, 12, 60, 40, 60, 60, 30, 12, 7])

    dev = ((g['pri'], g['title'], str(r['c'][0]), r['fix']) for g in groups if g['status'] == 'open' and g['owner'] == 'Developers' for r in g['rows'])
    sheet('Developer fixes', ['Priority', 'Issue', 'URL', 'Fix'], dev, [8, 40, 70, 80])
    wr = ((g['pri'], g['title'], str(r['c'][0]), r['fix']) for g in groups if g['status'] == 'open' and g['owner'] in ('Writers', 'SEO') for r in g['rows'])
    sheet('Writer and SEO fixes', ['Priority', 'Issue', 'URL', 'Fix'], wr, [8, 40, 70, 80])

    stl = {'pass': 'Pass', 'fail': 'Fail', 'warn': 'Partly', 'todo': 'Not checked here', 'na': 'Does not apply'}
    sheet('Checklist', ['Section', 'Check', 'What good looks like', 'Status', 'What the crawl shows', 'Owner', 'Severity'],
          ([sec['t'], it['c'], it['what'], stl[it['s']], it['e'], it['o'], it['v']] for sec in data['checklist']['sections'] for it in sec['items']),
          [30, 32, 60, 16, 70, 12, 10])

    def int_rows():
        for p in internal_tab(crawl):
            if not p['w']:
                yield [p['u'], p['t'], 0, '(no internal links)', '', '', '']
            for src, a, pos, n in p['w']:
                yield [p['u'], p['t'], p['n'], src, a, pos, n]
    sheet('Internal links', ['Page', 'Title', 'Linking pages', 'Linking page', 'Anchor', 'Position', 'Times'], int_rows(), [60, 40, 10, 60, 36, 12, 7])

    sheet('Broken links', ['Dead URL', 'Status', 'Kind', 'Linking page', 'Anchor / alt text', 'Position', 'Times', 'Fix'],
          ([b['d'], b['st'], b['k'], b['src'], b['a'], b['p'], b['n'], b['fix']] for b in broken_tab(res['groups'])), [60, 8, 10, 60, 30, 12, 7, 70])

    def ext_rows():
        for e in external_tab(crawl, cap=None):
            for src, a, pos, n in e['w']:
                yield [e['u'], e['st'], e['n'], src, a, pos, n]
    sheet('External links', ['External URL', 'Status', 'Linking pages', 'Linking page', 'Anchor', 'Position', 'Times'], ext_rows(), [60, 8, 10, 60, 30, 12, 7])

    if data['changes']:
        sheet('What changed', ['Issue', 'Before', 'Now', 'Fixed', 'New'],
              ([c['title'], c['before'], c['now'], c['fixed'], c['new']] for c in data['changes']), [50, 10, 10, 10, 10])

    wb.save(path)
    return True


def _plain(html):
    import re
    return re.sub(r'<[^>]+>', '', html).replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
