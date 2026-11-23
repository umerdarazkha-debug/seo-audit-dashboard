"""The issue checks. Each check returns one group:

    affected URL -> every linking page + anchor + position -> exact fix -> "done when"

A check that needs an export or column the crawl does not have is marked
status="skip" and is left out of the score.
"""
import difflib
import re
from collections import Counter, defaultdict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .crawl import TEMPLATE_POSITIONS, host_of, is_dead, to_float, to_int

DEV, WRITER, SEO = 'Developers', 'Writers', 'SEO'
CRAWL, LINKS, SITEMAP, ONPAGE, CONTENT, PERF, SECURITY, SCHEMA, EXTERNAL = (
    'Crawling and indexing', 'Internal links', 'XML sitemap', 'Titles and headings', 'Content and images',
    'Performance', 'Security', 'Structured data and hreflang', 'External links')
CATEGORIES = [CRAWL, LINKS, SITEMAP, ONPAGE, CONTENT, PERF, SECURITY, SCHEMA, EXTERNAL]

GENERIC_ANCHORS = {'click here', 'here', 'read more', 'learn more', 'more', 'this', 'link', 'this page', 'see more',
                   'find out more', 'continue reading', 'details', 'go', 'this article', 'check it out'}
BOT_BLOCK = {'401', '403', '406', '429', '999'}
NOT_FOUND = re.compile(r"\b(404|page not found|not found|page (does not|doesn't|can't|cannot) (exist|be found))\b", re.I)

WHERE_CAP = 200          # linking rows per affected URL in the HTML (the workbook keeps all)
SITEWIDE_MIN = 15        # same anchor in a template block on this many pages = one sitewide line


def pl(n, one, many=None):
    """'1 page', '3 pages'; with two forms, '1 page has' / '3 pages have'."""
    return f'{n:,} ' + (one if n == 1 else (many or one + 's'))


def vb(n, one, many):
    return one if n == 1 else many


def where(links, cap=None):
    """Linking pages for one URL as [source, anchor, position, count].
    Navigation / header / footer / sidebar links that repeat on many pages collapse into one line."""
    c = Counter((l.src, l.text, l.pos) for l in links)
    tmpl = defaultdict(set)
    for (s, a, p) in c:
        if p in TEMPLATE_POSITIONS:
            tmpl[(a, p)].add(s)
    out, folded = [], set()
    for (a, p), srcs in tmpl.items():
        if len(srcs) >= SITEWIDE_MIN:
            folded.add((a, p))
            out.append([f'Sitewide {p.lower()} ({len(srcs):,} pages, e.g. {sorted(srcs)[0]})', a, p, len(srcs)])
    for (s, a, p), n in sorted(c.items()):
        if (a, p) not in folded:
            out.append([s, a, p, n])
    return (out[:cap] if cap else out), len(out)


def row(cells, fix, links=None, pages=None, cap=None):
    r = {'c': cells, 'fix': fix}
    if links:
        r['w'], r['wn'] = where(links, cap)
        r['wk'] = 'links'
        r['np'] = len({l.src for l in links})
        site = [w for w in r['w'] if w[0].startswith('Sitewide ')]
        if site:
            r['fix'] += f'. The link is in the sitewide {site[0][2].lower()}: fix it once in the shared template'
    elif pages:
        pg = sorted(pages)
        r['w'] = [[u, d, '', 1] for u, d in (pg[:cap] if cap else pg)]
        r['wn'] = len(pg)
        r['wk'] = 'pages'
    return r


def strip_utm(u):
    p = urlsplit(u)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith('utm_')]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), p.fragment))


class Checks:
    def __init__(self, crawl):
        self.c = crawl
        self.groups = []
        live = {urlsplit(r['Address']).path.rstrip('/') or '/': r['Address'] for r in crawl.indexable}
        self._live_paths = live

    # ---------- plumbing ----------
    def add(self, id, title, cat, owner, pri, why, fix, done, cols, rows, code='', summary='', aff=None, need=None):
        """need: list of (ok, what is missing). Any failed need -> skip."""
        missing = [m for ok, m in (need or []) if not ok]
        g = {'id': id, 'title': title, 'cat': cat, 'owner': owner, 'pri': pri, 'sev': 'bad' if pri == 'P1' else 'warn',
             'why': why, 'fix': fix, 'done': done, 'code': code, 'cols': cols}
        if missing:
            g.update(status='skip', rows=[], aff=0, summary='Not checked: needs ' + ' and '.join(missing) + '.')
        else:
            g.update(status='open' if rows else 'pass', rows=rows, aff=(aff if aff is not None else len(rows)) if rows else 0,
                     summary=summary if rows else '')
        self.groups.append(g)

    def hyperlinks(self, pred):
        return [l for l in self.c.links if l.type == 'Hyperlink' and pred(l)]

    def closest(self, u):
        p = urlsplit(u).path.rstrip('/')
        parent, slug = p.rsplit('/', 1) if '/' in p else ('', p)
        cands = {k.rsplit('/', 1)[-1]: v for k, v in self._live_paths.items() if k.rsplit('/', 1)[0] == parent}
        m = difflib.get_close_matches(slug, list(cands), n=1, cutoff=0.75)
        return cands[m[0]] if m else ''

    def col(self, name):
        return (self.c.has_col(name), f'the "{name}" column in internal_all.csv')

    def file(self, key, what):
        return (self.c.have[key], what)

    # ---------- run ----------
    def run(self):
        for f in (self.broken, self.broken_res, self.server_errors, self.soft404, self.http_pages, self.redirects, self.chains,
                  self.temp_redirects, self.noindex_linked, self.canonicals, self.params, self.url_hygiene,
                  self.nofollow, self.utm, self.http_links, self.generic_anchors, self.few_inlinks, self.deep,
                  self.sitemap_bad, self.not_in_sitemap, self.orphans,
                  self.titles, self.meta, self.h1, self.h2, self.thin, self.exact_dup, self.near_dup, self.alt,
                  self.slow, self.heavy_html, self.heavy_img, self.compression, self.asset_cache,
                  self.mixed, self.sec_headers, self.sd_errors, self.schema_missing, self.hreflang, self.broken_ext):
            f()
        return self.groups

    NEED_INLINKS = 'all_inlinks.csv (bulk export "Links:All Inlinks")'

    # ---------- crawling and indexing ----------
    def broken(self):
        c = self.c
        dead = self.hyperlinks(lambda l: c.own(l.dst) and is_dead(l) and l.src in c.pages)
        g = defaultdict(list)
        for l in dead:
            g[l.dst].append(l)

        def fx(d):
            best = self.closest(d)
            if best:
                return f'Change the href to {best} (closest live URL, check it is the same topic), or remove the link and keep the text'
            return 'Link to a live page on the same topic, or remove the link and keep the text'
        rows = [row([d, ls[0].status if ls[0].status not in ('0', '') else (ls[0].stext or 'no response')], fx(d), ls) for d, ls in sorted(g.items(), key=lambda kv: -len(kv[1]))]
        srcs = {l.src for l in dead}
        self.add('broken', 'Broken internal links', LINKS, WRITER, 'P1',
                 'Visitors and Googlebot land on an error page, and the link passes no value to anything.',
                 'Open each linking page, find the link by its anchor text and change the href to the URL in the Fix column, or remove the link. '
                 'Links in a navigation, header or footer position live in a shared template: one edit there fixes every page.',
                 'A new crawl shows 0 internal links to 4xx, 5xx or no-response URLs.',
                 ['Dead URL', 'Status'], rows, aff=len(srcs),
                 summary=f'{pl(len(dead), "internal link")} on {pl(len(srcs), "page")} {vb(len(dead), "points", "point")} at {pl(len(g), "dead URL")}.',
                 need=[self.file('inlinks', self.NEED_INLINKS)])

    def broken_res(self):
        c = self.c
        bad = [l for l in c.links if l.type != 'Hyperlink' and is_dead(l) and l.src in c.pages]
        g = defaultdict(list)
        for l in bad:
            g[l.dst].append(l)
        rows = [row([d, ls[0].status if ls[0].status not in ('0', '') else (ls[0].stext or 'no response'), ls[0].type], 'Upload the file again at this path, or update the src/href in the template', ls)
                for d, ls in sorted(g.items(), key=lambda kv: -len(kv[1]))]
        self.add('broken-res', 'Broken images, scripts and stylesheets', CRAWL, DEV, 'P1',
                 'The page asks the browser for a file that is gone: a missing image, script or stylesheet. Users see a broken layout and Google renders an incomplete page.',
                 'Restore the file or fix the reference. Most of these sit in one shared component, so check the template first.',
                 'A new crawl shows 0 images, scripts, stylesheets or fonts returning 4xx, 5xx or no response.',
                 ['Missing file', 'Status', 'Type'], rows, aff=len({l.src for l in bad}),
                 summary=f'{pl(len(g), "missing file is", "missing files are")} requested by {pl(len({l.src for l in bad}), "page")}.',
                 need=[self.file('inlinks', self.NEED_INLINKS)])

    def server_errors(self):
        c = self.c
        errs = [r for r in c.pages.values() if c.own(r['Address']) and r.get('Status Code', '').startswith('5')]
        rows = [row([r['Address'], r['Status Code']], 'Check the server log for this URL at crawl time; fix the error or return a 404 if the page is gone', c.inl.get(r['Address']))
                for r in errs]
        self.add('server-errors', 'Server errors (5xx)', CRAWL, DEV, 'P1',
                 'A 5xx tells Google the server is failing. If it keeps happening, Google slows its crawling of the whole site and can drop the URLs.',
                 'Look up each URL in the server or CDN logs at the time of the crawl. If the errors only came under crawl load, lower the crawl speed and re-test, then fix the capacity issue.',
                 'A new crawl at normal speed shows 0 URLs returning 5xx.',
                 ['URL', 'Status'], rows, summary=f'{pl(len(errs), "URL")} returned a server error during the crawl.')

    def soft404(self):
        c = self.c
        hits = [r for r in c.live if NOT_FOUND.search(r.get('Title 1', '') or '') or NOT_FOUND.search(r.get('H1-1', '') or '')]
        rows = [row([r['Address'], r.get('Title 1', ''), r.get('H1-1', '')], 'Return HTTP 404 (or 410) for this URL, or 301 it to the closest live page', c.inl.get(r['Address']))
                for r in hits]
        code = ('// Next.js (App Router): call notFound() before anything streams\n'
                "import { notFound } from 'next/navigation'\n"
                'export default async function Page({ params }) {\n'
                '  const post = await getPost(params.slug)\n'
                '  if (!post) notFound()          // sends a real 404\n'
                '  return <Article post={post} />\n'
                '}\n\n'
                '# PHP\nhttp_response_code(404);\n\n'
                '# Express\nres.status(404).render("not-found")')
        self.add('soft404', 'Error pages that return 200 (soft 404)', CRAWL, DEV, 'P1',
                 'These pages say "not found" but send HTTP 200. Google keeps them in its queue, reports them as soft 404s, and link checkers cannot see that the links are broken.',
                 'Make the route send a real 404 status when the content does not exist. The page can still show your friendly not-found design.',
                 'Every URL in this list returns 404 or 410 (check with curl -I), and Search Console shows no new soft 404s.',
                 ['URL', 'Title', 'H1'], rows, code=code,
                 summary=f'{pl(len(hits), "page looks like an error page but returns", "pages look like error pages but return")} 200.')

    def http_pages(self):
        c = self.c
        hits = [r for r in c.live if r['Address'].startswith('http://')]
        rows = [row([r['Address']], 'Redirect to ' + r['Address'].replace('http://', 'https://', 1) + ' with a 301', c.inl.get(r['Address'])) for r in hits]
        code = ('# nginx\nserver {\n  listen 80;\n  server_name example.com www.example.com;\n  return 301 https://example.com$request_uri;\n}\n\n'
                '# Apache .htaccess\nRewriteEngine On\nRewriteCond %{HTTPS} off\nRewriteRule ^ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]')
        self.add('http-pages', 'Pages served over plain http', SECURITY, DEV, 'P1',
                 'Pages that load on http:// with a 200 are duplicates of the https version, and browsers mark them "Not secure".',
                 'Send a 301 from every http:// URL to the https:// URL, at the server or CDN.',
                 'Every http:// URL answers 301 to its https:// version in one hop.',
                 ['URL'], rows, code=code, summary=f'{pl(len(hits), "page loads", "pages load")} over http:// without redirecting to https.')

    def redirects(self):
        c = self.c
        red = self.hyperlinks(lambda l: c.own(l.dst) and l.status[:1] == '3' and l.src in c.pages)
        g = defaultdict(list)
        for l in red:
            g[l.dst].append(l)
        rows = []
        for d, ls in sorted(g.items(), key=lambda kv: -len(kv[1])):
            chain, fs = c.follow(d)
            final = chain[-1]
            if fs == '200':
                fx = f'Change the href to {final}'
            elif fs in ('?', ''):
                fx = f'Change the href to {final} (not crawled: check it loads)'
            else:
                fx = f'The redirect ends on {fs}: link to a live page instead, or remove the link'
            rows.append(row([d, ls[0].status, final, len(chain) - 1], fx, ls))
        self.add('redirects', 'Internal links that go through a redirect', LINKS, WRITER, 'P2',
                 'Each redirect costs the visitor an extra round trip and gives Google a mixed signal about which URL is the real one.',
                 'Change each href to the final URL shown in the Fix column. Template links (navigation, footer) are fixed once in the shared component.',
                 'A new crawl shows 0 internal links to 3xx URLs.',
                 ['Linked URL', 'Code', 'Ends at', 'Hops'], rows, aff=len({l.src for l in red}),
                 summary=f'{pl(len(red), "internal link")} on {pl(len({l.src for l in red}), "page")} {vb(len(red), "goes", "go")} through {pl(len(g), "redirect")}.',
                 need=[self.file('inlinks', self.NEED_INLINKS), self.col('Redirect URL')])

    def chains(self):
        c = self.c
        rows = []
        for u, r in c.pages.items():
            if c.own(u) and r.get('Status Code', '').startswith('3'):
                chain, fs = c.follow(u)
                if len(chain) > 2 or fs == 'loop':
                    rows.append(row([u, ' → '.join(chain[1:]), len(chain) - 1, fs],
                                    'Redirect loop: break it by sending this URL to one live page' if fs == 'loop' else f'Redirect {u} straight to {chain[-1]}',
                                    c.inl.get(u)))
        code = ('# nginx: one hop, straight to the final URL\nlocation = /old-page { return 301 https://example.com/new-page; }\n\n'
                '# Apache\nRedirect 301 /old-page https://example.com/new-page')
        self.add('chains', 'Redirect chains and loops', CRAWL, DEV, 'P3',
                 'Every extra hop slows the page down. Google stops following after a few hops, and a loop never resolves.',
                 'Update the redirect rules so the first URL points straight at the final URL.',
                 'Every redirect on the site resolves in one hop and none loop.',
                 ['Starts at', 'Path', 'Hops', 'Final status'], rows, code=code,
                 summary=f'{pl(len(rows), "redirect takes", "redirects take")} two or more hops or {vb(len(rows), "loops", "loop")}.',
                 need=[self.col('Redirect URL')])

    def temp_redirects(self):
        c = self.c
        hits = [r for u, r in c.pages.items() if c.own(u) and r.get('Status Code') in ('302', '303', '307') and c.inl.get(u)]
        rows = [row([r['Address'], r['Status Code'], r.get('Redirect URL', '')], 'If the move is permanent, change it to a 301 or 308', c.inl.get(r['Address'])) for r in hits]
        self.add('temp-redirects', 'Temporary redirects on linked URLs', CRAWL, DEV, 'P3',
                 'A 302 or 307 says the move is temporary, so Google may keep the old URL in its index.',
                 'Use 301 (or 308) for anything that is not coming back.',
                 'Every internally linked redirect is a 301 or 308, unless it is truly temporary.',
                 ['URL', 'Code', 'Goes to'], rows, summary=f'{pl(len(hits), "linked URL uses", "linked URLs use")} a temporary redirect.')

    def noindex_linked(self):
        c = self.c
        hits = [r for r in c.live if r.get('Indexability') == 'Non-Indexable' and 'noindex' in (r.get('Indexability Status', '') or '').lower()]
        rows = [row([r['Address'], r.get('Indexability Status', ''), to_int(r.get('Unique Inlinks'))],
                    'If the page should rank, remove the noindex. If not, remove or nofollow the internal links to it', c.inl.get(r['Address']))
                for r in hits if to_int(r.get('Unique Inlinks')) > 0]
        self.add('noindex-linked', 'Noindex pages that get internal links', CRAWL, SEO, 'P2',
                 'You are sending link value and crawl time to pages you told Google not to index. Sometimes that is right (login, cart); often a noindex was left on by mistake.',
                 'Go through the list. Pages that should rank: remove the noindex. Pages that should not: link to them less.',
                 'Every noindex page in this list is either indexable now or confirmed as intentional.',
                 ['URL', 'Reason', 'Linking pages'], rows, summary=f'{pl(len(rows), "noindex page receives", "noindex pages receive")} internal links.',
                 need=[self.col('Indexability Status')])

    def canonicals(self):
        c = self.c
        rows = []
        for r in c.live:
            u, can = r['Address'], (r.get('Canonical Link Element 1') or '').strip()
            if r.get('Indexability') == 'Indexable' and not can:
                rows.append(row([u, '(none)', 'Missing'], f'Add <link rel="canonical" href="{u}">'))
            elif can and can != u:
                st = c.status.get(can, '')
                if st and st != '200':
                    rows.append(row([u, can, f'Points at a {st} URL'], 'Point the canonical at a live 200 URL (usually this page itself)', c.inl.get(u)))
                elif can in c.pages and c.pages[can].get('Indexability') == 'Non-Indexable':
                    rows.append(row([u, can, 'Points at a noindex page'], 'Point the canonical at an indexable page', c.inl.get(u)))
        code = '<!-- in <head>, absolute URL, one per page -->\n<link rel="canonical" href="https://example.com/current-page">'
        self.add('canonicals', 'Canonical tag problems', CRAWL, DEV, 'P2',
                 'The canonical tag tells Google which URL to index. Missing or wrong canonicals let duplicates compete, or send Google to a page that cannot rank.',
                 'Print one absolute, self-referencing canonical on every indexable page from the page template. On duplicates, point it at the live, indexable original.',
                 'A new crawl shows every indexable page with a canonical, and no canonical pointing at a redirect, error or noindex URL.',
                 ['Page', 'Canonical', 'Problem'], rows, code=code, summary=f'{pl(len(rows), "page has", "pages have")} a missing or broken canonical.',
                 need=[self.col('Canonical Link Element 1')])

    def params(self):
        c = self.c
        hits = [r for r in c.indexable if '?' in r['Address']]
        rows = [row([r['Address']], f'Add a canonical to {r["Address"].split("?")[0]}, and stop linking to the parameter version', c.inl.get(r['Address'])) for r in hits]
        self.add('params', 'Indexable URLs with query strings', CRAWL, DEV, 'P3',
                 'Parameter URLs (sorting, filters, tracking) that are indexable create copies of the clean page and spread signals thin.',
                 'Canonical each parameter URL to the clean URL, and link to the clean URL internally.',
                 'A new crawl shows no indexable URL with a query string, unless it is a deliberate landing page.',
                 ['URL'], rows, summary=f'{pl(len(hits), "indexable URL carries a query string", "indexable URLs carry query strings")}.')

    def url_hygiene(self):
        c = self.c
        rows = []
        for r in c.indexable:
            p = urlsplit(r['Address']).path
            probs = []
            if p != p.lower():
                probs.append('uppercase letters')
            if '_' in p:
                probs.append('underscores')
            if len(r['Address']) > 115:
                probs.append(f'{len(r["Address"])} characters')
            if probs:
                rows.append(row([r['Address'], ', '.join(probs)], 'For new pages use short, lowercase, hyphenated slugs. Only change a live URL with a 301 from the old one'))
        self.add('url-hygiene', 'URLs that are long, use capitals or underscores', CRAWL, WRITER, 'P3',
                 'Short, lowercase, hyphenated URLs are easier to share and read. Mixed case also creates duplicates on servers that treat /Page and /page as different URLs.',
                 'Fix the slug rules for new content. Do not rename live URLs for this alone unless you also add a 301.',
                 'New pages follow the slug rules; any renamed URL has a 301 from the old one.',
                 ['URL', 'Problem'], rows, summary=f'{pl(len(rows), "URL is", "URLs are")} long, mixed-case or {vb(len(rows), "uses", "use")} underscores.')

    # ---------- internal links ----------
    def nofollow(self):
        c = self.c
        nf = self.hyperlinks(lambda l: c.own(l.dst) and (not l.follow or 'nofollow' in l.rel) and l.src in c.pages)
        g = defaultdict(list)
        for l in nf:
            g[l.dst].append(l)
        rows = [row([d], 'Remove rel="nofollow" from this link on each page listed', ls) for d, ls in sorted(g.items(), key=lambda kv: -len(kv[1]))]
        code = '<!-- before -->\n<a href="/pricing" rel="nofollow">Pricing</a>\n<!-- after -->\n<a href="/pricing">Pricing</a>'
        self.add('nofollow', 'Internal links marked nofollow', LINKS, DEV, 'P3',
                 'rel="nofollow" on your own links tells Google not to follow them, so your own pages get less internal link value.',
                 'Remove the nofollow from internal links. Keep it only on login or account links you do not want crawled.',
                 'A new crawl shows 0 nofollow internal links to indexable pages.',
                 ['Linked URL'], rows, code=code, aff=len({l.src for l in nf}),
                 summary=f'{pl(len(nf), "internal link")} on {pl(len({l.src for l in nf}), "page")} {vb(len(nf), "is", "are")} nofollow.',
                 need=[self.file('inlinks', self.NEED_INLINKS)])

    def utm(self):
        c = self.c
        hits = self.hyperlinks(lambda l: c.own(l.dst) and 'utm_' in l.dst.lower() and l.src in c.pages)
        rows = [row([l.src, l.dst, l.text], f'Change the href to {strip_utm(l.dst)}') for l in hits]
        self.add('utm', 'Internal links with UTM tags', LINKS, WRITER, 'P2',
                 'UTM tags on internal links reset the visitor\'s traffic source in analytics, and every tagged URL is one more duplicate for Google to crawl.',
                 'Use the clean URL for links between your own pages. Keep UTM tags for links from emails, ads and other sites.',
                 'A new crawl shows 0 internal links with utm_ parameters.',
                 ['Page to edit', 'Linked URL', 'Anchor'], rows, aff=len({l.src for l in hits}),
                 summary=f'{pl(len(hits), "internal link carries", "internal links carry")} UTM tags.',
                 need=[self.file('inlinks', self.NEED_INLINKS)])

    def http_links(self):
        c = self.c
        hits = self.hyperlinks(lambda l: c.own(l.dst) and l.dst.startswith('http://') and l.src in c.pages)
        g = defaultdict(list)
        for l in hits:
            g[l.dst].append(l)
        rows = [row([d], 'Change the href to ' + d.replace('http://', 'https://', 1), ls) for d, ls in sorted(g.items(), key=lambda kv: -len(kv[1]))]
        self.add('http-links', 'Internal links using http://', LINKS, WRITER, 'P3',
                 'Each http:// link forces a redirect to https and can show a security warning on some browsers.',
                 'Change the href to https://, or better, to a root-relative path like /pricing.',
                 'A new crawl shows 0 internal links starting with http://.',
                 ['Linked URL'], rows, aff=len({l.src for l in hits}),
                 summary=f'{pl(len(hits), "internal link still uses", "internal links still use")} http://.',
                 need=[self.file('inlinks', self.NEED_INLINKS)])

    def generic_anchors(self):
        c = self.c
        hits = self.hyperlinks(lambda l: c.own(l.dst) and l.pos in ('Content', '') and l.text.lower().strip(' .!→>»') in GENERIC_ANCHORS and l.src in c.pages)
        rows = [row([l.src, l.text, l.dst], 'Rewrite the anchor to say what the target page is about, e.g. "' + (c.pages.get(l.dst, {}).get('H1-1') or c.pages.get(l.dst, {}).get('Title 1') or 'pricing plans')[:60] + '"')
                for l in hits]
        self.add('generic-anchors', 'Generic anchor text ("click here", "read more")', LINKS, WRITER, 'P3',
                 'Anchor text tells Google and screen-reader users what the linked page is about. "Click here" tells them nothing.',
                 'Rewrite each anchor so it names the topic of the target page.',
                 'A new crawl shows 0 in-content links with generic anchors.',
                 ['Page to edit', 'Anchor', 'Links to'], rows, aff=len({l.src for l in hits}),
                 summary=f'{pl(len(hits), "in-content link uses", "in-content links use")} a generic anchor like "click here".',
                 need=[self.file('inlinks', self.NEED_INLINKS)])

    def few_inlinks(self):
        c = self.c
        home = c.site.rstrip('/')
        hits = [r for r in c.indexable if r['Address'].rstrip('/') != home and to_int(r.get('Unique Inlinks')) < 3]
        rows = [row([r['Address'], to_int(r.get('Unique Inlinks'))], 'Add in-content links from 2-3 related, indexable pages', c.inl.get(r['Address']))
                for r in sorted(hits, key=lambda r: to_int(r.get('Unique Inlinks')))]
        self.add('few-inlinks', 'Indexable pages with fewer than 3 internal links', LINKS, SEO, 'P2',
                 'Pages with almost no internal links look unimportant to Google and are hard for visitors to find.',
                 'For each page, pick two or three related pages and add a contextual link with a descriptive anchor.',
                 'Every indexable page has at least 3 unique internal links pointing at it.',
                 ['Page', 'Linking pages'], rows, summary=f'{pl(len(hits), "indexable page has", "indexable pages have")} fewer than 3 internal links.',
                 need=[self.col('Unique Inlinks')])

    def deep(self):
        c = self.c
        hits = [r for r in c.indexable if to_int(r.get('Crawl Depth')) >= 4]
        rows = [row([r['Address'], to_int(r.get('Crawl Depth'))], 'Link to it from a page 1-2 clicks from the homepage (a hub, category or popular post)')
                for r in sorted(hits, key=lambda r: -to_int(r.get('Crawl Depth')))]
        self.add('deep', 'Pages 4 or more clicks from the homepage', LINKS, SEO, 'P3',
                 'Deep pages are crawled less often and get little internal link value.',
                 'Add links from hub pages, categories or the navigation so important pages sit within 3 clicks.',
                 'No important page is more than 3 clicks from the homepage.',
                 ['Page', 'Clicks from home'], rows, summary=f'{pl(len(hits), "indexable page is", "indexable pages are")} 4+ clicks from the homepage.',
                 need=[self.col('Crawl Depth')])

    # ---------- sitemap ----------
    NEED_SITEMAP = 'a sitemap (use --sitemap, or put the XML files in a sitemap/ folder inside the crawl folder)'

    def sitemap_bad(self):
        c = self.c
        sm = c.sitemap_urls or set()
        rows = []
        for u in sorted(sm):
            r = c.pages.get(u)
            if not r:
                st = c.status.get(u)
                if st and st != '200':
                    rows.append(row([u, f'returns {st}'], 'Remove it from the sitemap'))
                continue
            sc = r.get('Status Code', '')
            if sc.startswith('3'):
                rows.append(row([u, f'redirects ({sc})'], f'List {r.get("Redirect URL", "the final URL")} instead'))
            elif sc != '200':
                rows.append(row([u, f'returns {sc}'], 'Remove it from the sitemap, and 301 the URL if it has links'))
            elif r.get('Indexability') == 'Non-Indexable':
                rows.append(row([u, (r.get('Indexability Status') or 'non-indexable').lower()], 'Remove it from the sitemap, or make the page indexable if it should rank'))
        code = ('// sitemap generator: only list live, indexable, canonical URLs\n'
                'const urls = pages.filter(p =>\n  p.status === 200 &&\n  !p.noindex &&\n  p.canonical === p.url\n)')
        self.add('sitemap-bad', 'Sitemap lists URLs that cannot be indexed', SITEMAP, DEV, 'P1',
                 'A sitemap should list only live, indexable, canonical URLs. Every redirect, error or noindex entry wastes crawl time and makes Google trust the file less.',
                 'Filter the sitemap generator so it only outputs URLs that return 200, are indexable and are their own canonical.',
                 'Every URL in the sitemap returns 200, is indexable and is self-canonical.',
                 ['Sitemap URL', 'Problem'], rows, code=code, summary=f'{pl(len(rows), "sitemap URL redirects, fails or is", "sitemap URLs redirect, fail or are")} noindex.',
                 need=[(c.sitemap_urls is not None, self.NEED_SITEMAP)])

    def not_in_sitemap(self):
        c = self.c
        sm = c.sitemap_urls or set()
        smn = {u.rstrip('/') for u in sm}
        hits = [r for r in c.indexable if c.on_main(r['Address']) and r['Address'].rstrip('/') not in smn and '?' not in r['Address']]
        rows = [row([r['Address']], 'Add to the sitemap if the page should rank; otherwise noindex it') for r in hits]
        self.add('not-in-sitemap', 'Indexable pages missing from the sitemap', SITEMAP, DEV, 'P2',
                 'Live pages that are not in the sitemap can only be found through links, so new or deep pages get picked up slowly.',
                 'Make sure the generator includes every page type (posts, categories, landing pages).',
                 'Every indexable page on the main host is listed in the sitemap.',
                 ['Page'], rows, summary=f'{pl(len(hits), "indexable page is", "indexable pages are")} not in the sitemap.',
                 need=[(c.sitemap_urls is not None, self.NEED_SITEMAP)])

    def orphans(self):
        c = self.c
        sm = c.sitemap_urls or set()
        linked = {l.dst.rstrip('/') for l in c.links if l.type == 'Hyperlink' and l.src != l.dst}
        hits = [u for u in sorted(sm) if c.pages.get(u, {}).get('Status Code') == '200' and u.rstrip('/') not in linked and u.rstrip('/') != c.site.rstrip('/')]
        rows = [row([u], 'Link to it from at least one related page, or remove it from the sitemap and 301 it') for u in hits]
        self.add('orphans', 'Sitemap pages with no internal links (orphans)', SITEMAP, WRITER, 'P2',
                 'No page on the site links to these. Google treats them as unimportant and visitors cannot reach them.',
                 'Add at least one contextual link from a related page. If the page is no longer wanted, drop it from the sitemap and redirect it.',
                 'Every sitemap URL has at least one internal link from an indexable page.',
                 ['Page'], rows, summary=f'{pl(len(hits), "sitemap page has", "sitemap pages have")} no internal links.',
                 need=[(c.sitemap_urls is not None, self.NEED_SITEMAP), self.file('inlinks', self.NEED_INLINKS)])

    # ---------- titles and headings ----------
    def _dupes(self, col):
        cnt = Counter((r.get(col) or '').strip().lower() for r in self.c.indexable)
        return {k for k, v in cnt.items() if k and v > 1}

    def titles(self):
        c = self.c
        dup = self._dupes('Title 1')
        rows = []
        for r in c.indexable:
            t = (r.get('Title 1') or '').strip()
            n = len(t)
            p = 'missing' if not t else 'duplicate' if t.lower() in dup else f'too long ({n})' if n > 60 else f'too short ({n})' if n < 30 else ''
            if p:
                rows.append(row([r['Address'], t, p], 'Write a unique title of 30-60 characters: main topic first, brand last'))
        self.add('titles', 'Title tags: missing, duplicate, too long or too short', ONPAGE, WRITER, 'P2',
                 'The title is the blue link in search results. Missing or duplicate titles make pages compete with each other; long ones get cut off.',
                 'Give each indexable page its own title, 30 to 60 characters, with the topic first.',
                 'A new crawl shows every indexable page with a unique title of 30-60 characters.',
                 ['Page', 'Title', 'Problem'], rows, summary=f'{pl(len(rows), "page has", "pages have")} a missing, duplicate or badly sized title.',
                 need=[self.col('Title 1')])

    def meta(self):
        c = self.c
        dup = self._dupes('Meta Description 1')
        rows = []
        for r in c.indexable:
            t = (r.get('Meta Description 1') or '').strip()
            n = len(t)
            p = 'missing' if not t else 'duplicate' if t.lower() in dup else f'too long ({n})' if n > 160 else f'too short ({n})' if n < 70 else ''
            if p:
                rows.append(row([r['Address'], t, p], 'Write a unique description of 70-160 characters that says what the reader gets'))
        self.add('meta', 'Meta descriptions: missing, duplicate, too long or too short', ONPAGE, WRITER, 'P3',
                 'Google often shows the description under the title. A clear, unique one earns more clicks; duplicates are usually ignored.',
                 'Write one per page, 70 to 160 characters, that matches what the page delivers.',
                 'A new crawl shows every indexable page with a unique description of 70-160 characters.',
                 ['Page', 'Description', 'Problem'], rows, summary=f'{pl(len(rows), "page has", "pages have")} a missing, duplicate or badly sized meta description.',
                 need=[self.col('Meta Description 1')])

    def h1(self):
        c = self.c
        dup = self._dupes('H1-1')
        rows = []
        for r in c.indexable:
            t = (r.get('H1-1') or '').strip()
            p = 'missing' if not t else 'more than one H1' if (r.get('H1-2') or '').strip() else 'duplicate' if t.lower() in dup else ''
            if p:
                rows.append(row([r['Address'], t, p], 'Use exactly one H1 per page that names the topic'))
        self.add('h1', 'H1 headings: missing, multiple or duplicate', ONPAGE, WRITER, 'P2',
                 'The H1 is the visible headline of the page. Each page needs one, and it should be different from every other page.',
                 'Add or rewrite the H1. If a template prints a second H1 (often the logo), change that element to a div or span.',
                 'Every indexable page has exactly one H1, and no two pages share one.',
                 ['Page', 'H1', 'Problem'], rows, summary=f'{pl(len(rows), "page has", "pages have")} a missing, repeated or duplicate H1.',
                 need=[self.col('H1-1')])

    def h2(self):
        c = self.c
        hits = [r for r in c.indexable if not (r.get('H2-1') or '').strip() and to_int(r.get('Word Count')) >= 300]
        rows = [row([r['Address'], to_int(r.get('Word Count'))], 'Break the text into sections with descriptive H2 headings') for r in hits]
        self.add('h2', 'Long pages with no H2 headings', ONPAGE, WRITER, 'P3',
                 'Sub-headings help readers scan, and give Google and AI answer engines clear sections to quote.',
                 'Add H2s that describe each section, ideally in the words people search with.',
                 'Every indexable page over 300 words has at least one H2.',
                 ['Page', 'Words'], rows, summary=f'{pl(len(hits), "page over 300 words has", "pages over 300 words have")} no H2.',
                 need=[self.col('H2-1'), self.col('Word Count')])

    # ---------- content and images ----------
    def thin(self):
        c = self.c
        home = c.site.rstrip('/')
        hits = [r for r in c.indexable if to_int(r.get('Word Count')) < 300 and r['Address'].rstrip('/') != home]
        rows = [row([r['Address'], to_int(r.get('Word Count')), r.get('Title 1', '')], 'Expand it with useful detail, merge it into a stronger page (with a 301), or noindex it')
                for r in sorted(hits, key=lambda r: to_int(r.get('Word Count')))]
        self.add('thin', 'Thin pages (under 300 words)', CONTENT, WRITER, 'P3',
                 'Indexable pages with very little text rarely rank, and many of them can lower how Google rates the site overall. Some page types (contact, pricing) are fine short.',
                 'Review the list: expand the pages that should rank, merge near-empty ones, and noindex the rest.',
                 'Every indexable page under 300 words is either expanded, merged or confirmed as fine short.',
                 ['Page', 'Words', 'Title'], rows, summary=f'{pl(len(hits), "indexable page has", "indexable pages have")} under 300 words.',
                 need=[self.col('Word Count')])

    def exact_dup(self):
        c = self.c
        g = defaultdict(list)
        for r in c.indexable:
            if r.get('Hash'):
                g[r['Hash']].append(r['Address'])
        rows = [row([us[0], len(us)], 'Keep one URL; 301 or canonical the others to it', pages=[(u, 'same content') for u in us[1:]])
                for us in g.values() if len(us) > 1]
        self.add('exact-dup', 'Exact duplicate pages', CONTENT, WRITER, 'P2',
                 'Two indexable URLs with identical content compete with each other. Google picks one and may pick the wrong one.',
                 'Choose the URL to keep. Redirect the copies to it, or point their canonical at it.',
                 'No two indexable URLs share the same content hash.',
                 ['Kept URL', 'Copies'], rows, aff=sum(len(us) for us in g.values() if len(us) > 1),
                 summary=f'{pl(len(rows), "page has an exact duplicate", "pages have exact duplicates")} at other URLs.',
                 need=[self.col('Hash')])

    def near_dup(self):
        c = self.c
        hits = [r for r in c.indexable if to_int(r.get('No. Near Duplicates')) > 0]
        rows = [row([r['Address'], r.get('Closest Near Duplicate Match', ''), to_int(r.get('No. Near Duplicates'))],
                    'Make each page clearly different, or merge them into one and 301 the other') for r in hits]
        self.add('near-dup', 'Near-duplicate pages', CONTENT, WRITER, 'P2',
                 'Pages that are 90% the same split ranking signals. Google usually shows only one of them.',
                 'Merge pages that serve the same search, or rewrite them so each targets a different need.',
                 'A new crawl with near-duplicate detection on shows 0 near-duplicates among indexable pages.',
                 ['Page', 'Closest match', 'Near duplicates'], rows, summary=f'{pl(len(hits), "page is a near-duplicate", "pages are near-duplicates")} of another page.',
                 need=[self.col('No. Near Duplicates')])

    def alt(self):
        c = self.c
        hits = [l for l in c.links if l.type == 'Image' and not l.text and l.pos == 'Content' and l.src in c.pages and c.pages[l.src].get('Status Code') == '200']
        g = defaultdict(list)
        for l in hits:
            g[l.dst].append(l)
        rows = [row([d], 'Add alt text that describes the image (leave alt="" only for decoration)', ls) for d, ls in sorted(g.items(), key=lambda kv: -len(kv[1]))]
        code = '<img src="/img/dashboard.png" alt="Sales dashboard showing revenue by month" width="1200" height="675">'
        self.add('alt', 'Content images with no alt text', CONTENT, WRITER, 'P3',
                 'Alt text is how screen readers and Google Images understand a picture. Screenshots, charts and product photos need it.',
                 'Write a short description of what the image shows. Decorative images can keep an empty alt.',
                 'A new crawl shows 0 in-content images with an empty alt, apart from decoration.',
                 ['Image'], rows, code=code, aff=len({l.src for l in hits}),
                 summary=f'{pl(len(g), "content image")} on {pl(len({l.src for l in hits}), "page")} {vb(len(g), "has", "have")} no alt text.',
                 need=[self.file('inlinks', self.NEED_INLINKS)])

    # ---------- performance ----------
    def slow(self):
        c = self.c
        hits = [r for r in c.live if to_float(r.get('Response Time')) > 1.5]
        rows = [row([r['Address'], f'{to_float(r.get("Response Time")):.2f} s'], 'Cache the page at the CDN or speed up the server work behind it')
                for r in sorted(hits, key=lambda r: -to_float(r.get('Response Time')))]
        self.add('slow', 'Slow server response (over 1.5 s)', PERF, DEV, 'P2',
                 'A slow first byte delays everything that follows. It hurts Largest Contentful Paint and Google crawls slow sites less.',
                 'Serve these pages from a cache (static generation or CDN caching), and profile the slow database or API calls behind them.',
                 'Every page responds in under 0.8 s in a fresh crawl (crawler timing, not lab data).',
                 ['Page', 'Response time'], rows, summary=f'{pl(len(hits), "page")} took over 1.5 s to respond.',
                 need=[self.col('Response Time')])

    def heavy_html(self):
        c = self.c
        hits = [r for r in c.live if to_int(r.get('Size (Bytes)')) > 500_000]
        rows = [row([r['Address'], f'{to_int(r.get("Size (Bytes)")) // 1024:,} KB'], 'Move inlined data, SVGs or base64 images out of the HTML') for r in hits]
        self.add('heavy-html', 'HTML documents over 500 KB', PERF, DEV, 'P3',
                 'Very large HTML, usually from inlined JSON, SVGs or base64 images, slows parsing on every page view.',
                 'Load big data on demand, reference images as files, and trim the data the framework embeds in the page.',
                 'No HTML document is over 500 KB.',
                 ['Page', 'Size'], rows, summary=f'{pl(len(hits), "HTML page is", "HTML pages are")} over 500 KB.',
                 need=[self.col('Size (Bytes)')])

    def heavy_img(self):
        c = self.c
        big = {u: s for u, s in c.images.items() if s > 200_000 and c.own(u)}
        rows = [row([u, f'{s // 1024:,} KB'], 'Resize to the displayed width and convert to WebP or AVIF (aim for under 150 KB)', c.inl.get(u))
                for u, s in sorted(big.items(), key=lambda kv: -kv[1])]
        code = ('# convert and resize\ncwebp -q 80 -resize 1600 0 hero.png -o hero.webp\n\n'
                '<img src="/img/hero-1600.webp"\n     srcset="/img/hero-800.webp 800w, /img/hero-1600.webp 1600w"\n'
                '     sizes="(max-width: 800px) 100vw, 800px" width="1600" height="900" alt="...">')
        self.add('heavy-img', 'Images over 200 KB', PERF, DEV, 'P2',
                 'Oversized images are the most common reason for a slow Largest Contentful Paint on mobile.',
                 'Resize each image to the size it is shown at, serve WebP or AVIF, and use srcset for different screens.',
                 'No image on the site is over 200 KB.',
                 ['Image', 'Size'], rows, code=code, aff=len({l.src for u in big for l in c.inl.get(u, [])}) or len(big),
                 summary=f'{pl(len(big), "image is", "images are")} over 200 KB.',
                 need=[(bool(c.images), 'image sizes (export "Images:All")')])

    def compression(self):
        c = self.c
        col = 'Response Header: Content-Encoding'
        hits = [r for r in c.live if not (r.get(col) or '').strip()]
        rows = [row([r['Address']], 'Enable gzip or brotli for text/html') for r in hits]
        code = '# nginx\ngzip on;\ngzip_types text/html text/css application/javascript application/json image/svg+xml;\n# or brotli on; with the brotli module'
        self.add('compression', 'HTML served without compression', PERF, DEV, 'P2',
                 'Uncompressed HTML is several times larger on the wire, which slows the first paint on mobile.',
                 'Turn on gzip or brotli at the server or CDN.',
                 'Every HTML response has Content-Encoding: br or gzip.',
                 ['Page'], rows, code=code, summary=f'{pl(len(hits), "HTML page is", "HTML pages are")} sent uncompressed.',
                 need=[self.col(col)])

    def asset_cache(self):
        c = self.c
        col = 'Response Header: Cache-Control'
        rows = []
        for u, r in c.pages.items():
            ct = r.get('Content-Type', r.get('Content Type', ''))
            if not c.own(u) or not ct.startswith(('text/css', 'application/javascript', 'text/javascript', 'image/', 'font/')) or r.get('Status Code') != '200':
                continue
            cc = (r.get(col) or '').lower()
            m = re.search(r'max-age=(\d+)', cc)
            if 'immutable' in cc or (m and int(m.group(1)) >= 604800):
                continue
            rows.append(row([u, cc or '(none)'], 'Send Cache-Control: public, max-age=31536000, immutable (use hashed file names)'))
        code = '# versioned static files (file name changes when content changes)\nCache-Control: public, max-age=31536000, immutable'
        self.add('asset-cache', 'Static files with a short browser cache', PERF, DEV, 'P3',
                 'Without a long cache, returning visitors download the same CSS, JS and images again on every visit.',
                 'Give fingerprinted static files a one-year cache.',
                 'Every static file on the site has a max-age of at least 7 days.',
                 ['File', 'Cache-Control'], rows, code=code, summary=f'{pl(len(rows), "static file has", "static files have")} a short or missing cache header.',
                 need=[self.col(col)])

    # ---------- security ----------
    def mixed(self):
        c = self.c
        hits = [l for l in c.links if l.type != 'Hyperlink' and l.dst.startswith('http://') and l.src.startswith('https://') and l.src in c.pages]
        g = defaultdict(list)
        for l in hits:
            g[l.dst].append(l)
        rows = [row([d, ls[0].type], 'Change the reference to https://', ls) for d, ls in g.items()]
        code = '<!-- quick safety net while you fix the references -->\n<meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">'
        self.add('mixed', 'Mixed content (http files on https pages)', SECURITY, DEV, 'P1',
                 'Browsers block or warn about http:// images and scripts on an https page.',
                 'Change every reference to https:// (or a relative path).',
                 'A new crawl shows 0 http:// resources on https pages.',
                 ['File', 'Type'], rows, code=code, aff=len({l.src for l in hits}),
                 summary=f'{pl(len(g), "http:// file loads", "http:// files load")} on {pl(len({l.src for l in hits}), "https page")}.',
                 need=[self.file('inlinks', self.NEED_INLINKS)])

    def sec_headers(self):
        c = self.c
        want = [('Strict-Transport-Security', 'max-age=31536000; includeSubDomains'), ('X-Content-Type-Options', 'nosniff'),
                ('X-Frame-Options', 'SAMEORIGIN (or CSP frame-ancestors)'), ('Referrer-Policy', 'strict-origin-when-cross-origin')]
        have_any = any(k.startswith('Response Header:') for k in c.cols)
        rows = []
        for h, v in want:
            col = 'Response Header: ' + h
            miss = [r['Address'] for r in c.live if not (r.get(col) or '').strip()]
            if miss:
                rows.append(row([h, f'{len(miss):,} of {len(c.live):,} pages'], f'Send {h}: {v}', pages=[(u, 'missing') for u in miss]))
        code = ('# nginx\nadd_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;\n'
                'add_header X-Content-Type-Options "nosniff" always;\nadd_header X-Frame-Options "SAMEORIGIN" always;\n'
                'add_header Referrer-Policy "strict-origin-when-cross-origin" always;')
        self.add('sec-headers', 'Security headers missing', SECURITY, DEV, 'P3',
                 'These headers protect visitors from downgrade, sniffing and clickjacking attacks. They are not a ranking factor, but they are cheap to add.',
                 'Add them once at the server or CDN so every response carries them.',
                 'Every HTML response carries the four headers.',
                 ['Header', 'Missing on'], rows, code=code, aff=max((r['wn'] for r in rows), default=0),
                 summary=f'{pl(len(rows), "recommended security header is", "recommended security headers are")} missing.',
                 need=[(have_any, 'HTTP headers in the export (Config > Extraction > HTTP Headers)')])

    # ---------- structured data and hreflang ----------
    def sd_errors(self):
        c = self.c
        hits = [(u, s) for u, s in c.schema.items() if s['errors'] > 0]
        rows = [row([u, ', '.join(s['types']), s['errors']], 'Fix the errors shown in the Rich Results Test for this URL') for u, s in hits]
        code = ('<script type="application/ld+json">\n{\n  "@context": "https://schema.org",\n  "@type": "Article",\n'
                '  "headline": "Same text as the H1",\n  "datePublished": "2026-01-15",\n  "dateModified": "2026-03-02",\n'
                '  "author": { "@type": "Person", "name": "Author Name", "url": "https://example.com/authors/author-name" },\n'
                '  "image": "https://example.com/img/cover.jpg"\n}\n</script>')
        self.add('sd-errors', 'Structured data with validation errors', SCHEMA, DEV, 'P1',
                 'Google ignores invalid structured data, so the page loses any rich result it could have had.',
                 'Run each URL through the Rich Results Test and fix the required properties in the template that prints the JSON-LD.',
                 'A new crawl with structured data validation on shows 0 errors.',
                 ['Page', 'Types', 'Errors'], rows, code=code, summary=f'{pl(len(hits), "page has", "pages have")} structured data errors.',
                 need=[self.file('structured', 'structured_data_all.csv (export "Structured Data:All" with validation on)')])

    def schema_missing(self):
        c = self.c
        sec = defaultdict(list)
        for r in c.indexable:
            if not c.schema.get(r['Address'], {}).get('types'):
                seg = urlsplit(r['Address']).path.strip('/').split('/')[0]
                sec['/' + seg + ('/' if seg else '')].append(r['Address'])
        rows = [row([s, len(us)], 'Add JSON-LD to this template (Article for posts, Product for products, Organization and WebSite on the homepage, BreadcrumbList everywhere)',
                    pages=[(u, 'no schema') for u in us]) for s, us in sorted(sec.items(), key=lambda kv: -len(kv[1]))]
        code = ('<script type="application/ld+json">\n{\n  "@context": "https://schema.org",\n  "@type": "BreadcrumbList",\n  "itemListElement": [\n'
                '    { "@type": "ListItem", "position": 1, "name": "Home", "item": "https://example.com/" },\n'
                '    { "@type": "ListItem", "position": 2, "name": "Blog", "item": "https://example.com/blog/" }\n  ]\n}\n</script>')
        self.add('schema-missing', 'Indexable pages with no structured data', SCHEMA, DEV, 'P2',
                 'Structured data helps Google understand the page type and is needed for rich results like breadcrumbs, products and articles.',
                 'Add JSON-LD per template, not per page: one change covers every page in the folder.',
                 'Every indexable template prints valid JSON-LD for its page type.',
                 ['Folder', 'Pages without schema'], rows, aff=sum(len(us) for us in sec.values()),
                 code=code, summary=f'{pl(sum(len(us) for us in sec.values()), "indexable page has", "indexable pages have")} no structured data.',
                 need=[self.file('structured', 'structured_data_all.csv (export "Structured Data:All")')])

    def hreflang(self):
        c = self.c
        rows = []
        for u, tags in c.hreflang.items():
            targets = [t for _, t in tags]
            if u not in targets:
                rows.append(row([u, '', 'no self-reference'], 'Add an hreflang tag pointing at the page itself'))
            for lang, t in tags:
                st = c.status.get(t, '')
                if st and st != '200':
                    rows.append(row([u, f'{lang} → {t}', f'target returns {st}'], 'Point the tag at the live, indexable version of the page'))
                elif t in c.hreflang and u not in [x for _, x in c.hreflang[t]]:
                    rows.append(row([u, f'{lang} → {t}', 'no return tag'], f'Add a tag on {t} pointing back to this page'))
        code = ('<link rel="alternate" hreflang="en" href="https://example.com/page">\n'
                '<link rel="alternate" hreflang="de" href="https://example.com/de/page">\n'
                '<link rel="alternate" hreflang="x-default" href="https://example.com/page">')
        self.add('hreflang', 'hreflang errors', SCHEMA, DEV, 'P2',
                 'hreflang only works when every language version lists all the others and itself, and every target is live.',
                 'Print the full set of alternates, including the page itself and x-default, from one shared source in the template.',
                 'Every hreflang set is complete, reciprocal and points at 200, indexable URLs.',
                 ['Page', 'Tag', 'Problem'], rows, code=code, summary=f'{pl(len(rows), "hreflang problem")} found.',
                 need=[self.file('hreflang', 'hreflang_all.csv (export "Hreflang:All")')])

    # ---------- external ----------
    def broken_ext(self):
        c = self.c
        bad = self.hyperlinks(lambda l: not c.own(l.dst) and l.dst.startswith('http') and (is_dead(l) or l.status in BOT_BLOCK) and l.src in c.pages)
        g = defaultdict(list)
        for l in bad:
            g[l.dst].append(l)
        rows = []
        for d, ls in sorted(g.items(), key=lambda kv: (kv[1][0].status in BOT_BLOCK, -len(kv[1]))):
            st = ls[0].status if ls[0].status not in ('0', '') else (ls[0].stext or 'no response')
            fx = ('Probably blocks crawlers: open it in a browser and leave it if it loads' if st in BOT_BLOCK
                  else 'Replace it with a live source, or remove the link')
            rows.append(row([d, st], fx, ls))
        dead_srcs = {l.src for l in bad if l.status not in BOT_BLOCK}
        self.add('broken-ext', 'Broken external links', EXTERNAL, WRITER, 'P3',
                 'Links to other sites that now return an error look neglected to readers. A 401, 403, 429 or 999 usually means the other site blocks crawlers, not that the page is gone.',
                 'Replace dead links with a live source or remove them. Check the crawler-blocked ones in a browser first.',
                 'A new crawl shows 0 external links returning 404, 410, 5xx or no response.',
                 ['External URL', 'Status'], rows, aff=len(dead_srcs),
                 summary=f'{pl(len(g), "external URL")} linked from {pl(len({l.src for l in bad}), "page")} {vb(len(g), "returns", "return")} an error or {vb(len(g), "blocks", "block")} the crawler.',
                 need=[self.file('inlinks', self.NEED_INLINKS)])
