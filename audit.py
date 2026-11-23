#!/usr/bin/env python3
"""Turn a Screaming Frog crawl export into a developer-ready SEO audit.

    python audit.py --crawl crawl/ --site https://example.com --out report/
    python audit.py --crawl crawl-new/ --previous crawl-old/ --site https://example.com --out report/

Writes report/seo-audit.html (one self-contained file, works offline) and report/seo-audit.xlsx.
"""
import argparse
import os
import sys
import time

from seo_audit.crawl import Crawl
from seo_audit.report import analyse, build, run_checklist, write_html
from seo_audit.workbook import write_xlsx


def main(argv=None):
    ap = argparse.ArgumentParser(description='Screaming Frog crawl export -> SEO audit dashboard (HTML) + workbook (XLSX).')
    ap.add_argument('--crawl', required=True, help='folder with the Screaming Frog CSV exports (internal_all.csv, all_inlinks.csv, ...)')
    ap.add_argument('--site', required=True, help='the site you crawled, e.g. https://example.com (subdomains count as the same site)')
    ap.add_argument('--out', default='report', help='output folder (default: report)')
    ap.add_argument('--previous', help='an older crawl folder of the same site, to show what changed')
    ap.add_argument('--sitemap', help='sitemap URL or local XML file (default: sitemap/*.xml or sitemap_urls.txt in the crawl folder)')
    ap.add_argument('--name', default='seo-audit', help='base name for the output files (default: seo-audit)')
    ap.add_argument('--no-xlsx', action='store_true', help='skip the Excel workbook')
    ap.add_argument('-q', '--quiet', action='store_true')
    a = ap.parse_args(argv)

    t0 = time.time()
    crawl = Crawl(a.crawl, a.site, a.sitemap, a.quiet)
    res = analyse(crawl)
    prev = prev_res = None
    if a.previous:
        prev = Crawl(a.previous, a.site, None, True)
        prev_res = analyse(prev)
    checklist = run_checklist(crawl, res, bool(a.previous))

    # folder names only: never put local paths in the report
    name = lambda p: os.path.basename(os.path.normpath(p)) if p else ''
    data = build(crawl, res, prev_res, name(a.previous), name(a.crawl), checklist)

    os.makedirs(a.out, exist_ok=True)
    html_path = os.path.join(a.out, a.name + '.html')
    write_html(data, html_path)
    xlsx_path = os.path.join(a.out, a.name + '.xlsx')
    wrote_xlsx = False if a.no_xlsx else write_xlsx(data, res, crawl, xlsx_path)

    if not a.quiet:
        g = res['groups']
        print(f'Health score: {res["score"]}/100 ({data["verdict"]})'
              + (f', was {prev_res["score"]}' if prev_res else ''))
        print(f'Issues: {sum(x["status"] == "open" for x in g)} open, {sum(x["status"] == "pass" for x in g)} passed, '
              f'{sum(x["status"] == "skip" for x in g)} not checked')
        print(f'Checklist: {checklist["total"]} checks, ' + ', '.join(f'{k} {v}' for k, v in sorted(checklist['counts'].items())))
        print(f'Wrote {html_path}' + (f' and {xlsx_path}' if wrote_xlsx else '') + f' in {time.time() - t0:.1f} s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
