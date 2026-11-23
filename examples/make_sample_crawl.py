#!/usr/bin/env python3
"""Build a SYNTHETIC Screaming Frog export for a made-up outdoor shop on example.com.

Nothing here comes from a real crawl. The site, pages and problems are invented so the
sample report has something to show. It writes two crawl folders, an older one and a
newer one, so the "what changed" view has data:

    python examples/make_sample_crawl.py
    python audit.py --crawl examples/sample-crawl --previous examples/sample-crawl-previous \
        --site https://example.com --out examples/sample-report
"""
import csv
import hashlib
import os
import random
from collections import defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = 'https://example.com'
BRAND = 'Example Outdoor'

PRODUCTS = ['tent-2p', 'tent-4p', 'ultralight-tarp', 'trekking-poles', 'down-sleeping-bag', 'synthetic-sleeping-bag', 'sleeping-pad',
            'camp-stove', 'titanium-pot', 'water-filter', 'headlamp', 'daypack-20l', 'backpack-45l', 'backpack-65l', 'rain-jacket',
            'fleece-midlayer', 'merino-base-layer', 'hiking-boots', 'trail-runners', 'gaiters', 'camp-chair', 'hammock', 'bear-canister', 'tent-2p-green']
POSTS = ['how-to-choose-a-tent', 'winter-camping-guide', 'packing-list-for-a-weekend-hike', 'how-to-clean-a-sleeping-bag', 'best-camp-stoves',
         'tent-vs-tarp', 'layering-for-cold-weather', 'how-to-pitch-a-tent-in-wind', 'water-filters-compared', 'beginner-backpacking-checklist',
         'how-to-break-in-hiking-boots', 'trail-runners-vs-boots', 'camping-with-kids', 'leave-no-trace-basics', 'how-to-store-a-down-bag',
         'choosing-a-sleeping-pad', 'hammock-camping-guide', 'bear-safety-in-camp', 'headlamp-buying-guide', 'how-to-waterproof-a-jacket',
         'first-overnight-hike', 'budget-backpacking-gear', 'how-to-pack-a-backpack', 'campsite-cooking-ideas', 'rain-camping-tips',
         'merino-vs-synthetic', 'trekking-poles-explained', 'how-to-read-a-topo-map', 'altitude-basics-for-hikers', 'spring-gear-checklist']
CATS = ['tents', 'packs', 'sleep', 'kitchen', 'clothing']
EXTERNAL = {  # invented sites on reserved domains (RFC 2606 / RFC 6761)
    'https://www.example.org/outdoor-safety-guide': '200', 'https://www.example.org/weather-tables': '200',
    'https://parks.example.net/permits': '200', 'https://parks.example.net/old-trail-map': '404',
    'https://maker.example/tent-fabric-study': '200', 'https://maker.example/warranty': '301',
    'https://forum.example/threads/stove-fuel': '200', 'https://forum.example/threads/deleted-thread': '410',
    'https://video.example/watch/pitch-a-tent': '200', 'https://social.example/exampleoutdoor': '999',
    'https://news.example/2021/gear-review': '0', 'https://research.example.org/water-safety.pdf': '200',
}


def nohex(s):
    """A fake content hash (letters g-n instead of a-f)."""
    return hashlib.sha1(s.encode()).hexdigest().translate(str.maketrans('abcdef', 'ghjkmn'))[:32]


def build(state):
    """state = 'previous' (older crawl) or 'current'."""
    cur = state == 'current'
    rnd = random.Random(11 if cur else 7)
    P = {}   # url -> page dict
    L = []   # links: (type, src, dst, text, pos, follow, rel)

    def page(path, **kw):
        u = SITE + path
        d = {'status': '200', 'ctype': 'text/html; charset=utf-8', 'title': '', 'meta': '', 'h1': '', 'h1b': '', 'h2': '', 'words': 600,
             'canonical': u, 'robots': '', 'size': 42000, 'rt': 0.25, 'hash': nohex(path + state), 'redirect': '', 'rtype': '',
             'enc': 'br', 'schema': [], 'sd_err': 0, 'near': 0, 'near_to': '', 'flesch': 62, 'cc': 'public, max-age=0, must-revalidate'}
        d.update(kw)
        P[u] = d
        return u

    def a(src, dst, text, pos='Content', follow=True, rel='', typ='Hyperlink'):
        L.append((typ, src, dst if dst.startswith('http') else SITE + dst, text, pos, follow, rel))

    # ---------- pages ----------
    home = page('/', title=f'Camping and Hiking Gear | {BRAND}', meta='Tents, packs, sleeping bags and stoves for weekend trips and long trails. Free returns within 60 days.',
                h1='Gear for your next trip outside', h2='Shop by category', words=820, schema=['Organization', 'WebSite'])
    page('/products/', title=f'All Products | {BRAND}', meta='Browse every tent, pack, sleeping bag, stove and layer we sell, with honest specs and sizes.', h1='All products', h2='Tents', words=420, schema=['BreadcrumbList'])
    for c in CATS:
        page(f'/category/{c}/', title=f'{c.title()} | {BRAND}', meta=f'Our {c} range, tested on real trips. Compare weights, prices and sizes side by side.', h1=c.title(), h2='Best sellers', words=380)
    for i, p in zip(range(len(PRODUCTS)), PRODUCTS):
        name = p.replace('-', ' ').title()
        page(f'/products/{p}', title=f'{name} | {BRAND}', meta=f'The {name.lower()}: weight, materials, sizes and what our testers thought after a season of use.',
             h1=name, h2='Specs', words=rnd.randint(420, 900), schema=['Product', 'BreadcrumbList'], size=rnd.randint(52000, 98000))
    page('/blog/', title=f'Camping and Hiking Guides | {BRAND}', meta='Guides and gear advice from our staff: how to choose, pack, pitch and care for your gear.', h1='Guides', h2='Latest guides', words=350, schema=['BreadcrumbList'])
    for i, p in zip(range(len(POSTS)), POSTS):
        name = p.replace('-', ' ').capitalize()
        page(f'/blog/{p}', title=f'{name} | {BRAND}', meta=f'{name}: a plain guide from people who camp every month, with the gear we actually carry.',
             h1=name, h2='What you need', words=rnd.randint(900, 2400), schema=['BlogPosting', 'BreadcrumbList'], flesch=rnd.randint(48, 72))
    page('/about', title=f'About Us | {BRAND}', meta='Who we are, where we test our gear and how we choose what to sell. Small team, lots of nights outside.', h1='About us', h2='How we test', words=640)
    page('/contact', title=f'Contact | {BRAND}', meta='Questions about an order or a product? Reach our support team by email or chat, every day 8am to 8pm.', h1='Contact us', words=140)
    page('/privacy', title=f'Privacy Policy | {BRAND}', meta='How we collect, use and protect your data when you shop with us or read our guides.', h1='Privacy policy', h2='What we collect', words=1800, flesch=28)
    page('/terms', title=f'Terms of Service | {BRAND}', meta='The terms that apply when you buy from us: orders, returns, warranties and liability.', h1='Terms of service', h2='Orders', words=2100, flesch=24)
    page('/shipping', title=f'Shipping and Returns | {BRAND}', meta='Delivery times, costs and our 60-day return policy, explained in plain words.', h1='Shipping and returns', h2='Delivery times', words=520)
    page('/authors/editorial-team', title=f'Our Editorial Team | {BRAND}', meta='The people who write and test for our guides, with their experience and the trips behind each review.', h1='Editorial team', h2='How we write', words=450, schema=['Person'])
    page('/guides/packing-checklist', title=f'Printable Packing Checklist | {BRAND}', meta='A one-page checklist for overnight trips. Print it, tick it, forget nothing at the trailhead.', h1='Packing checklist', h2='Shelter', words=700)

    # ---------- planted problems ----------
    # redirects, chains, errors, soft 404s
    page('/shop', status='301', redirect=SITE + '/products/', rtype='HTTP Redirect', ctype='text/html', title='', h1='', words=0)
    page('/sale', status='301', redirect=SITE + '/deals', rtype='HTTP Redirect', ctype='text/html', words=0)
    page('/deals', status='301', redirect=SITE + '/products/', rtype='HTTP Redirect', ctype='text/html', words=0)
    page('/gift-cards', status='302', redirect=SITE + '/products/', rtype='HTTP Redirect', ctype='text/html', words=0)
    page('/blog/winter-camping-tips', status='301', redirect=SITE + '/blog/winter-camping-guide', rtype='HTTP Redirect', ctype='text/html', words=0)
    P['http://example.com/about'] = dict(P[SITE + '/about'], status='301', redirect=SITE + '/about', rtype='HTTP Redirect', words=0, title='', h1='')
    page('/blog/best-tents-2023', status='404', title='Page not found', h1='', words=60, canonical='', schema=[])
    page('/products/trail-runner-x', status='404', title='Page not found', h1='', words=60, canonical='', schema=[])
    page('/stores', status='503', title='', h1='', words=0, canonical='')
    page('/blog/tag/old-news', title=f'Page not found | {BRAND}', h1='Sorry, this page does not exist', words=40, meta='')
    if cur:
        page('/careers', status='404', title='Page not found', words=60, canonical='')
    else:
        page('/blog/news', status='404', title='Page not found', words=60, canonical='')
    page('/blog/draft-gear-list', robots='noindex, follow', title=f'Draft gear list | {BRAND}', h1='Draft gear list', words=300, schema=['BlogPosting'])
    page('/products/?sort=price', title=f'All Products | {BRAND}', meta='Browse every tent, pack, sleeping bag, stove and layer we sell, with honest specs and sizes.', h1='All products', words=420, canonical='')
    page('/Old_Page', title=f'Old Page | {BRAND}', h1='Old page', words=210, meta='')

    # on-page and content problems
    P[SITE + '/products/tent-2p-green']['hash'] = P[SITE + '/products/tent-2p']['hash']
    P[SITE + '/products/tent-2p-green']['title'] = P[SITE + '/products/tent-2p']['title']
    P[SITE + '/products/tent-2p-green']['h1'] = P[SITE + '/products/tent-2p']['h1']
    P[SITE + '/products/camp-chair']['title'] = ''
    P[SITE + '/products/hammock']['title'] = 'Hammock'
    P[SITE + '/blog/how-to-store-a-down-bag'].update(near=1, near_to=SITE + '/blog/how-to-clean-a-sleeping-bag')
    P[SITE + '/blog/how-to-clean-a-sleeping-bag'].update(near=1, near_to=SITE + '/blog/how-to-store-a-down-bag')
    for p in ('beginner-backpacking-checklist', 'spring-gear-checklist', 'budget-backpacking-gear'):
        P[SITE + f'/blog/{p}']['title'] = f'The Complete and Totally Up to Date {p.replace("-", " ").title()} for Every Season | {BRAND}'
    for p in ('camping-with-kids', 'rain-camping-tips', 'how-to-read-a-topo-map', 'altitude-basics-for-hikers') + (() if cur else ('first-overnight-hike', 'campsite-cooking-ideas', 'merino-vs-synthetic')):
        P[SITE + f'/blog/{p}']['meta'] = ''
    P[SITE + '/blog/tent-vs-tarp']['meta'] = P[SITE + '/blog/how-to-choose-a-tent']['meta'] = 'Read our guide.'
    P[SITE + '/category/kitchen/']['h1'] = ''
    P[SITE + '/blog/hammock-camping-guide']['h1b'] = BRAND
    P[SITE + '/category/packs/']['h1'] = 'Tents'
    P[SITE + '/blog/leave-no-trace-basics']['h2'] = ''
    P[SITE + '/blog/how-to-read-a-topo-map']['h2'] = ''
    for p in ('gaiters', 'bear-canister'):
        P[SITE + f'/products/{p}']['words'] = rnd.randint(150, 260)
    P[SITE + '/blog/altitude-basics-for-hikers']['title'] = f'Altitude Basics for Hikers (2022) | {BRAND}'
    for p in ('headlamp', 'water-filter', 'titanium-pot'):
        P[SITE + f'/products/{p}']['canonical'] = ''
    P[SITE + '/products/daypack-20l']['canonical'] = SITE + '/products/trail-runner-x'
    for p in ('backpack-65l', 'down-sleeping-bag') + (() if cur else ('tent-4p', 'camp-stove', 'rain-jacket')):
        P[SITE + f'/products/{p}']['sd_err'] = 2
    if not cur:  # the older crawl still served this page on plain http
        P['http://example.com/shipping'] = dict(P[SITE + '/shipping'], hash=nohex('http-shipping'), canonical='http://example.com/shipping')
    # performance
    for p, t in (('/products/', 2.4), ('/blog/', 1.9), ('/category/tents/', 1.7)) + (() if cur else (('/products/tent-4p', 2.2),)):
        P[SITE + p]['rt'] = t
    P[SITE + '/blog/campsite-cooking-ideas']['size'] = 655000
    for p in ('/about', '/terms'):
        P[SITE + p]['enc'] = ''
    if not cur:
        for p in ('/contact', '/shipping', '/privacy'):
            P[SITE + p]['enc'] = ''

    # assets
    def asset(path, ctype, size, cc='public, max-age=31536000, immutable', status='200'):
        u = SITE + path
        P[u] = {'status': status, 'ctype': ctype, 'size': size, 'rt': 0.08, 'cc': cc, 'asset': True}
        return u
    asset('/assets/app.css', 'text/css', 38000, cc='public, max-age=3600')
    asset('/assets/app.js', 'application/javascript', 145000, cc='public, max-age=3600')
    asset('/img/logo.svg', 'image/svg+xml', 4200)
    asset('/img/old-banner.jpg', 'image/jpeg', 0, status='404')
    hero = {}
    for p in PRODUCTS[:12]:
        big = p in ('tent-2p', 'tent-4p', 'backpack-65l', 'rain-jacket', 'hiking-boots', 'camp-stove')
        hero[p] = asset(f'/img/products/{p}.jpg', 'image/jpeg', rnd.randint(240000, 610000) if big else rnd.randint(60000, 150000))

    # ---------- links ----------
    live_html = [u for u, d in P.items() if not d.get('asset') and d['status'] == '200' and u.startswith(SITE)]
    for u in live_html:
        a(u, '/assets/app.css', '', 'Head', typ='CSS')
        a(u, '/assets/app.js', '', 'Head', typ='JavaScript')
        a(u, '/img/logo.svg', BRAND, 'Header', typ='Image')
        a(u, '/', 'Home', 'Navigation')
        a(u, '/shop', 'Shop', 'Navigation')
        a(u, '/blog/', 'Guides', 'Navigation')
        a(u, '/about', 'About', 'Navigation')
        for f, t in (('/contact', 'Contact'), ('/shipping', 'Shipping and returns'), ('/privacy', 'Privacy'), ('/terms', 'Terms')):
            a(u, f, t, 'Footer')
        if cur:
            a(u, '/careers', 'Careers', 'Footer')
        else:
            a(u, '/blog/news', 'News', 'Navigation')
        a(u, 'https://social.example/exampleoutdoor', 'Follow us', 'Footer')
    a(SITE + '/', '/products/', 'Shop all gear')
    for c in CATS:
        a(SITE + '/', f'/category/{c}/', c.title())
        a(SITE + '/products/', f'/category/{c}/', c.title())
    for i, p in zip(range(len(PRODUCTS)), PRODUCTS):
        cat = CATS[i % len(CATS)]
        a(SITE + f'/category/{cat}/', f'/products/{p}', p.replace('-', ' ').title())
        if i < 16:
            a(SITE + '/products/', f'/products/{p}', p.replace('-', ' ').title())
        if p in hero:
            a(SITE + f'/products/{p}', f'/img/products/{p}.jpg', p.replace('-', ' ') if i % 4 else '', typ='Image')
    a(SITE + '/category/tents/', '/products/?sort=price', 'Sort by price')
    a(SITE + '/', '/blog/', 'Read our guides')
    # blog index links to the newest 12 posts, the rest are only reachable deeper
    for p in POSTS[:12]:
        a(SITE + '/blog/', f'/blog/{p}', p.replace('-', ' ').capitalize())
    for i in range(12, len(POSTS)):
        a(SITE + f'/blog/{POSTS[i - 6]}', f'/blog/{POSTS[i]}', POSTS[i].replace('-', ' '))
    for i, p in zip(range(len(POSTS)), POSTS):
        src = SITE + f'/blog/{p}'
        for q in rnd.sample(PRODUCTS[:22], 3):
            a(src, f'/products/{q}', q.replace('-', ' '))
        if i % 3 != 2:
            for k in (1, 2):
                nb = POSTS[(i + k) % len(POSTS)]
                a(src, f'/blog/{nb}', nb.replace('-', ' '))
        if i % 5 == 1:
            a(src, '/img/old-banner.jpg', 'Spring sale', typ='Image')
        if i % 4 == 2:
            a(src, SITE + f'/img/products/{PRODUCTS[i % 12]}.jpg', '', typ='Image')
        a(src, '/authors/editorial-team', 'Our editorial team', 'Aside')
    # planted link problems
    for p in ('how-to-choose-a-tent', 'tent-vs-tarp', 'camping-with-kids') + (() if cur else ('first-overnight-hike', 'rain-camping-tips')):
        a(SITE + f'/blog/{p}', '/blog/best-tents-2023', 'our tent picks for 2023')
    for p in ('trail-runners-vs-boots', 'how-to-break-in-hiking-boots'):
        a(SITE + f'/blog/{p}', '/products/trail-runner-x', 'Trail Runner X')
    for p in ('layering-for-cold-weather', 'how-to-store-a-down-bag', 'rain-camping-tips', 'spring-gear-checklist'):
        a(SITE + f'/blog/{p}', '/blog/winter-camping-tips', 'winter camping tips')
    for p in ('budget-backpacking-gear', 'campsite-cooking-ideas'):
        a(SITE + f'/blog/{p}', '/sale', 'current deals')
    a(SITE + '/blog/', '/gift-cards', 'Gift cards')
    a(SITE + '/about', 'http://example.com/about', 'about us')
    a(SITE + '/about', '/stores', 'Find a store')
    a(SITE + '/blog/', '/blog/tag/old-news', 'Old news')
    for p in ('packing-list-for-a-weekend-hike', 'first-overnight-hike'):
        a(SITE + f'/blog/{p}', '/blog/draft-gear-list', 'full gear list')
    for p in ('how-to-pitch-a-tent-in-wind', 'best-camp-stoves', 'water-filters-compared', 'headlamp-buying-guide'):
        a(SITE + f'/blog/{p}', '/contact', 'ask our team', follow=False, rel='nofollow')
    for p in ('best-camp-stoves', 'beginner-backpacking-checklist') + (() if cur else ('how-to-pack-a-backpack', 'hammock-camping-guide')):
        a(SITE + f'/blog/{p}', '/products/camp-stove?utm_source=newsletter&utm_medium=email', 'camp stove')
    for p, t in (('how-to-clean-a-sleeping-bag', 'click here'), ('choosing-a-sleeping-pad', 'read more'), ('how-to-waterproof-a-jacket', 'here'),
                 ('trekking-poles-explained', 'click here')):
        a(SITE + f'/blog/{p}', f'/products/{rnd.choice(PRODUCTS[:20])}', t)
    a(SITE + '/blog/tent-vs-tarp', '/products/tent-2p-green', 'two-person tent')
    a(SITE + '/blog/water-filters-compared', 'http://cdn.example.net/widgets/compare.js', '', 'Content', typ='JavaScript')
    a(SITE + '/blog/hammock-camping-guide', '/Old_Page', 'older hammock notes')
    # external links
    ext_src = [SITE + f'/blog/{p}' for p in POSTS]
    for i, (e, st) in zip(range(len(EXTERNAL)), EXTERNAL.items()):
        if 'social.example' in e:
            continue
        for s in ext_src[i::7]:
            a(s, e, ['park permits', 'weather tables', 'safety guide', 'fabric study', 'warranty', 'forum thread', 'video', 'review', 'study'][i % 9])

    # ---------- depth and inlinks ----------
    out = defaultdict(set)
    inn = defaultdict(set)
    for typ, s, d, *_ in L:
        if typ == 'Hyperlink':
            out[s].add(d)
            inn[d].add(s)
    depth = {SITE + '/': 0}
    dq = deque([SITE + '/'])
    while dq:
        u = dq.popleft()
        tgt = P.get(u, {}).get('redirect') if P.get(u, {}).get('status', '').startswith('3') else None
        nxt = [tgt] if tgt else out[u]
        for v in nxt:
            if v and v not in depth and v.startswith(SITE):
                depth[v] = depth[u] + 1
                dq.append(v)
    for u, d in P.items():
        d['depth'] = depth.get(u, '')
        d['inl'] = len(inn[u])
        d['outl'] = len(out[u])
    return P, L


def status_text(sc):
    return {'200': 'OK', '301': 'Moved Permanently', '302': 'Found', '404': 'Not Found', '410': 'Gone', '503': 'Service Unavailable',
            '999': 'Request denied', '0': 'Connection Timeout'}.get(sc, '')


def write(state, folder):
    P, L = build(state)
    cur = state == "current"
    os.makedirs(os.path.join(folder, 'sitemap'), exist_ok=True)
    W = lambda name, head, rows: _w(os.path.join(folder, name), head, rows)

    head = ['Address', 'Content Type', 'Status Code', 'Status', 'Indexability', 'Indexability Status', 'Title 1', 'Title 1 Length',
            'Meta Description 1', 'Meta Description 1 Length', 'H1-1', 'H1-1 Length', 'H1-2', 'H1-2 Length', 'H2-1', 'H2-1 Length',
            'Meta Robots 1', 'Canonical Link Element 1', 'Size (Bytes)', 'Word Count', 'Flesch Reading Ease Score', 'Crawl Depth',
            'Inlinks', 'Unique Inlinks', 'Unique Outlinks', 'Closest Near Duplicate Match', 'No. Near Duplicates', 'Hash', 'Response Time',
            'Redirect URL', 'Redirect Type', 'HTTP Version', 'Response Header: Cache-Control', 'Response Header: Content-Encoding',
            'Response Header: Strict-Transport-Security', 'Response Header: X-Content-Type-Options', 'Response Header: X-Frame-Options',
            'Response Header: Referrer-Policy']
    rows = []
    for u, d in P.items():
        sc = d['status']
        if d.get('asset'):
            idx, why = ('Indexable', '') if sc == '200' else ('Non-Indexable', 'Client Error')
            rows.append([u, d['ctype'], sc, status_text(sc), idx, why] + [''] * 12 + [d['size'], '', '', d['depth'], d['inl'], d['inl'], 0, '', '', '',
                        d['rt'], '', '', '2', d['cc'], '', 'max-age=31536000', '', '', ''])
            continue
        if sc.startswith('3'):
            idx, why = 'Non-Indexable', 'Redirected'
        elif sc.startswith('4'):
            idx, why = 'Non-Indexable', 'Client Error'
        elif sc.startswith('5'):
            idx, why = 'Non-Indexable', 'Server Error'
        elif 'noindex' in d['robots']:
            idx, why = 'Non-Indexable', 'noindex'
        elif d['canonical'] and d['canonical'] != u:
            idx, why = 'Non-Indexable', 'Canonicalised'
        else:
            idx, why = 'Indexable', ''
        live = sc == '200'
        rows.append([u, d['ctype'], sc, status_text(sc), idx, why, d['title'], len(d['title']), d['meta'], len(d['meta']), d['h1'], len(d['h1']),
                     d['h1b'], len(d['h1b']), d['h2'], len(d['h2']), d['robots'], d['canonical'] if live else '', d['size'] if live else 1200,
                     d['words'] if live else 0, d['flesch'] if live else '', d['depth'], d['inl'], d['inl'], d['outl'], d['near_to'], d['near'],
                     d['hash'] if live else '', d['rt'], d['redirect'], d['rtype'], '2', d['cc'] if live else '', d['enc'] if live else '',
                     'max-age=31536000' if live else '', '', 'SAMEORIGIN' if live else '', 'strict-origin-when-cross-origin' if live else ''])
    W('internal_all.csv', head, rows)

    lh = ['Type', 'Source', 'Destination', 'Size (Bytes)', 'Alt Text', 'Anchor', 'Status Code', 'Status', 'Crawlability', 'Follow', 'Target', 'Rel',
          'Path Type', 'Link Path', 'Link Position', 'Link Origin']
    st = lambda d: P[d]['status'] if d in P else EXTERNAL.get(d, '200')
    W('all_inlinks.csv', lh, [[t, s, d, '', txt if t == 'Image' else '', txt if t != 'Image' else '', st(d), status_text(st(d)), 'Crawlable',
                               'true' if f else 'false', '', rel, 'Absolute', '', pos, 'HTML'] for t, s, d, txt, pos, f, rel in L])
    W('response_codes_all.csv', ['Address', 'Content Type', 'Status Code', 'Status', 'Indexability', 'Indexability Status', 'Inlinks', 'Response Time', 'Redirect URL', 'Redirect Type'],
      [[u, d['ctype'], d['status'], status_text(d['status']), '', '', d['inl'], d['rt'], d.get('redirect', ''), ''] for u, d in P.items()] +
      [[e, 'text/html', s, status_text(s), '', '', 1, 0.4, 'https://maker.example/support/warranty' if s == '301' else '', ''] for e, s in EXTERNAL.items()])
    W('structured_data_all.csv', ['Address', 'Errors', 'Warnings', 'Rich Result Errors', 'Rich Result Warnings', 'Rich Result Features', 'Feature-1', 'Total Types', 'Unique Types', 'Type-1', 'Type-2', 'Indexability', 'Indexability Status'],
      [[u, d['sd_err'], 0, d['sd_err'], 0, '', '', len(d['schema']), len(d['schema'])] + (d['schema'] + ['', ''])[:2] + ['Indexable', '']
       for u, d in P.items() if not d.get('asset') and d['status'] == '200' and d['schema']])
    W('images_all.csv', ['Address', 'Content Type', 'Size (Bytes)', 'IMG Inlinks', 'Indexability', 'Indexability Status', 'Dimensions'],
      [[u, d['ctype'], d['size'], d['inl'], 'Indexable', '', ''] for u, d in P.items() if d.get('asset') and d['ctype'].startswith('image/')])
    W('hreflang_all.csv', ['Address', 'Title 1', 'Occurrences', 'HTML hreflang 1', 'HTML hreflang 1 URL', 'Indexability', 'Indexability Status'], [])

    # sitemap: most indexable pages, a few stale entries, a few pages missing
    sm = [u for u, d in P.items() if not d.get('asset') and d['status'] == '200' and u.startswith(SITE) and '?' not in u and 'noindex' not in d['robots']
          and u not in (SITE + '/blog/tag/old-news', SITE + '/Old_Page')]
    sm = [u for u in sm if not u.endswith(('/products/gaiters', '/products/bear-canister', '/blog/spring-gear-checklist'))]
    sm += [SITE + '/blog/best-tents-2023', SITE + '/shop', SITE + '/blog/draft-gear-list']
    if not cur:
        sm += [SITE + '/products/trail-runner-x']
    with open(os.path.join(folder, 'sitemap', 'sitemap.xml'), 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for u in sm:
            f.write(f'  <url><loc>{u}</loc><lastmod>2026-0{"9" if cur else "6"}-15</lastmod></url>\n')
        f.write('</urlset>\n')
    with open(os.path.join(folder, 'README.txt'), 'w', encoding='utf-8') as f:
        f.write('SYNTHETIC SAMPLE DATA. A made-up shop on example.com (a reserved domain), generated by examples/make_sample_crawl.py.\n'
                'It mimics the files Screaming Frog exports. Nothing here comes from a real website.\n')
    print(f'{folder}: {len(P)} URLs, {len(L)} links, {len(sm)} sitemap URLs')


def _w(path, head, rows):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(head)
        w.writerows(rows)


if __name__ == '__main__':
    write('previous', os.path.join(HERE, 'sample-crawl-previous'))
    write('current', os.path.join(HERE, 'sample-crawl'))
