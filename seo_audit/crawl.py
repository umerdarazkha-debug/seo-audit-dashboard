"""Read a Screaming Frog export folder into one Crawl object.

Only internal_all.csv is required. Every other export adds checks; when a file
or a column is missing, the checks that need it are reported as "not checked"
instead of passing.
"""
import csv
import glob
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from urllib.parse import urlsplit

csv.field_size_limit(1 << 30)

# file name Screaming Frog writes -> short key used in this tool
FILES = {
    'internal': 'internal_all.csv',
    'inlinks': 'all_inlinks.csv',
    'responses': 'response_codes_all.csv',
    'structured': 'structured_data_all.csv',
    'images': 'images_all.csv',
    'hreflang': 'hreflang_all.csv',
    'content': 'content_all.csv',
    'security': 'security_all.csv',
    'sitemaps': 'sitemaps_all.csv',
}

HTML_TYPES = ('text/html', 'application/xhtml')
TEMPLATE_POSITIONS = {'Navigation', 'Header', 'Footer', 'Aside'}


def read_csv(path):
    """Stream rows as dicts. Screaming Frog writes UTF-8 with a BOM."""
    with open(path, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            yield r


def host_of(u):
    try:
        return urlsplit(u).netloc.lower()
    except ValueError:
        return ''


def to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


class Link:
    """One link from the 'All Inlinks' bulk export. __slots__ keeps big crawls in memory."""
    __slots__ = ('type', 'src', 'dst', 'text', 'status', 'stext', 'follow', 'rel', 'pos')

    def __init__(self, r):
        it = sys.intern
        self.type = it(r.get('Type', ''))
        self.src = it(r.get('Source', ''))
        self.dst = it(r.get('Destination', ''))
        self.text = (r.get('Anchor') or r.get('Alt Text') or '').strip()
        self.status = it(r.get('Status Code', '') or '')
        self.stext = it(r.get('Status', '') or '')
        self.follow = (r.get('Follow', 'true') or 'true').lower() != 'false'
        self.rel = (r.get('Rel') or '').lower()
        self.pos = it(r.get('Link Position', '') or '')


def is_dead(l):
    """4xx, 5xx, or no response. Status 0 also covers URLs the crawler skipped on purpose
    (for example "Blocked by robots.txt"); those are not broken links."""
    if l.status[:1] in '45':
        return True
    if l.status in ('0', ''):
        return 'blocked' not in l.stext.lower()
    return False


class Crawl:
    def __init__(self, folder, site, sitemap=None, quiet=False):
        self.folder = folder
        self.site = site.rstrip('/')
        if '://' not in self.site:
            self.site = 'https://' + self.site
        self.host = host_of(self.site)
        self.main = self.host[4:] if self.host.startswith('www.') else self.host
        self.have = {k: os.path.exists(os.path.join(folder, v)) for k, v in FILES.items()}
        if not self.have['internal']:
            raise SystemExit(f'internal_all.csv not found in {os.path.basename(os.path.abspath(folder))}/. '
                             'Export "Internal:All" from Screaming Frog first (see README).')
        self.quiet = quiet
        self._load_pages()
        self._load_links()
        self._load_extra()
        self.sitemap_urls, self.sitemap_source = self._load_sitemap(sitemap)

    # ---------- helpers ----------
    def log(self, *a):
        if not self.quiet:
            print(*a, file=sys.stderr)

    def own(self, u):
        h = host_of(u)
        return h == self.main or h.endswith('.' + self.main)

    def on_main(self, u):
        return host_of(u) in (self.main, 'www.' + self.main)

    def short(self, u):
        for pre in ('https://' + self.host, 'http://' + self.host):
            if u.startswith(pre):
                return u[len(pre):] or '/'
        return u

    def has_col(self, col):
        return col in self.cols

    # ---------- loading ----------
    def _load_pages(self):
        self.pages = {}
        path = os.path.join(self.folder, FILES['internal'])
        cols = None
        for r in read_csv(path):
            if cols is None:
                cols = set(r.keys())
            self.pages[r['Address']] = r
        self.cols = cols or set()
        self.html = [r for r in self.pages.values() if r.get('Content Type', '').startswith(HTML_TYPES) and self.own(r['Address'])]
        self.live = [r for r in self.html if r.get('Status Code') == '200']
        self.indexable = [r for r in self.live if r.get('Indexability', 'Indexable') == 'Indexable']
        self.log(f'pages: {len(self.pages):,} URLs, {len(self.html):,} HTML on the site, {len(self.indexable):,} indexable')

    def _load_links(self):
        self.links = []
        self.inl = defaultdict(list)   # destination -> [Link]
        if not self.have['inlinks']:
            return
        keep_types = {'Hyperlink', 'Image', 'JavaScript', 'CSS', 'Iframe', 'Font', 'Video', 'Audio'}
        for r in read_csv(os.path.join(self.folder, FILES['inlinks'])):
            if r.get('Type') not in keep_types:
                continue
            ln = Link(r)
            self.links.append(ln)
            self.inl[ln.dst].append(ln)
        self.log(f'links: {len(self.links):,} rows from all_inlinks.csv')

    def _load_extra(self):
        # status for every URL, internal or external
        self.status = {u: r.get('Status Code', '') for u, r in self.pages.items()}
        if self.have['responses']:
            for r in read_csv(os.path.join(self.folder, FILES['responses'])):
                self.status.setdefault(r['Address'], r.get('Status Code', ''))
        for ln in self.links:
            self.status.setdefault(ln.dst, ln.status)
        self.schema = {}
        if self.have['structured']:
            for r in read_csv(os.path.join(self.folder, FILES['structured'])):
                types = [r[k] for k in r if k and k.startswith('Type-') and r[k]]
                self.schema[r['Address']] = {'errors': to_int(r.get('Errors')), 'warnings': to_int(r.get('Warnings')), 'types': types}
        self.hreflang = defaultdict(list)
        if self.have['hreflang']:
            for r in read_csv(os.path.join(self.folder, FILES['hreflang'])):
                for k, v in r.items():
                    m = re.match(r'(HTML|HTTP|Sitemap) hreflang (\d+)$', k or '')
                    if m and v:
                        self.hreflang[r['Address']].append((v, r.get(f'{m.group(1)} hreflang {m.group(2)} URL', '')))
        self.images = {}
        if self.have['images']:
            for r in read_csv(os.path.join(self.folder, FILES['images'])):
                self.images[r['Address']] = to_int(r.get('Size (Bytes)'))
        for u, r in self.pages.items():
            if r.get('Content Type', '').startswith('image/'):
                self.images.setdefault(u, to_int(r.get('Size (Bytes)')))

    def _load_sitemap(self, sitemap):
        """Sitemap membership: --sitemap (URL or file), else sitemap/*.xml or sitemap_urls.txt in the crawl folder."""
        urls, src = set(), ''
        cands = []
        if sitemap:
            cands = [sitemap]
            src = sitemap if sitemap.startswith('http') else os.path.basename(sitemap)
        else:
            cands = sorted(glob.glob(os.path.join(self.folder, 'sitemap', '*.xml')) + glob.glob(os.path.join(self.folder, 'sitemap*.xml')))
            txt = os.path.join(self.folder, 'sitemap_urls.txt')
            if os.path.exists(txt):
                urls |= {l.strip() for l in open(txt, encoding='utf-8') if l.strip()}
                src = 'sitemap_urls.txt'
            if cands:
                src = ', '.join(os.path.relpath(c, self.folder) for c in cands)
        seen = set()

        def read(ref, depth=0):
            if ref in seen or depth > 3:
                return
            seen.add(ref)
            try:
                if ref.startswith('http'):
                    req = urllib.request.Request(ref, headers={'User-Agent': 'seo-audit-dashboard'})
                    data = urllib.request.urlopen(req, timeout=30).read()
                else:
                    data = open(ref, 'rb').read()
                root = ET.fromstring(data)
            except Exception as e:  # a bad sitemap should not stop the audit
                self.log(f'sitemap: could not read {ref}: {e}')
                return
            ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
            if root.tag.endswith('sitemapindex'):
                for loc in root.iter(ns + 'loc'):
                    child = loc.text.strip()
                    if not ref.startswith('http'):
                        local = os.path.join(os.path.dirname(ref), os.path.basename(urlsplit(child).path))
                        child = local if os.path.exists(local) else child
                    read(child, depth + 1)
            else:
                for loc in root.iter(ns + 'loc'):
                    if loc.text:
                        urls.add(loc.text.strip())

        for c in cands:
            read(c)
        if urls:
            self.log(f'sitemap: {len(urls):,} URLs')
        return (urls if (urls or src) else None), src

    # ---------- redirects ----------
    def follow(self, u, limit=10):
        """Follow redirects through the crawl. Returns (chain, final_status)."""
        chain = [u]
        cur = u
        for _ in range(limit):
            r = self.pages.get(cur)
            if not r:
                return chain, self.status.get(cur, '?') or '?'
            sc = r.get('Status Code', '')
            nxt = r.get('Redirect URL', '')
            if sc.startswith('3') and nxt:
                if nxt in chain:
                    return chain + [nxt], 'loop'
                chain.append(nxt)
                cur = nxt
                continue
            return chain, sc
        return chain, 'too many hops'
