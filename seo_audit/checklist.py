"""The full SEO audit checklist: 16 sections.

Each check is (name, what good looks like, owner, severity, how):
  owner     D = Developers, W = Writers, S = SEO
  severity  C = Critical, H = High, M = Medium, L = Low
  how       'g:<id>|<id>'  answered by issue checks in checks.py
            'f:<name>'     answered by a small function below
            'n:<key>'      needs a tool this crawl cannot see (marked "not checked here", never guessed)

Statuses: pass, fail, warn, todo (needs another tool), na (does not apply).
"""
import re
from collections import Counter
from urllib.parse import urlsplit

from .crawl import to_int

OWNER = {'D': 'Developers', 'W': 'Writers', 'S': 'SEO'}
SEV = {'C': 'Critical', 'H': 'High', 'M': 'Medium', 'L': 'Low'}
NEEDS = {
    'GSC': 'Needs Google Search Console',
    'BWT': 'Needs Bing Webmaster Tools',
    'LOGS': 'Needs server or CDN logs',
    'LINKS': 'Needs a backlink tool (Ahrefs, Semrush, Majestic)',
    'GA': 'Needs your analytics tool',
    'AI': 'Needs an AI visibility tracker or a manual prompt test',
    'MAN': 'Needs a manual review',
    'PSI': 'Needs PageSpeed Insights or CrUX field data',
    'RANK': 'Needs a rank tracker',
    'LIVE': 'Needs a live check of the site (curl or a browser)',
    'COMP': 'Needs a crawl and backlink data for each competitor',
}

SECTIONS = [
    ('1. Crawlability', [
        ('Robots file exists', 'robots.txt returns 200 as plain text on every host you want crawled.', 'D', 'L', 'n:LIVE'),
        ('Robots rules', 'No rule blocks pages, CSS, JS or images that Google needs to render the site.', 'D', 'H', 'n:LIVE'),
        ('Sitemap reference', 'robots.txt lists every XML sitemap with an absolute URL.', 'D', 'L', 'n:LIVE'),
        ('Sitemap content', 'Only live, indexable, self-canonical URLs are in the sitemap.', 'D', 'H', 'g:sitemap-bad'),
        ('Sitemap limits', 'Each file stays under 50,000 URLs and 50 MB; big sites use a sitemap index.', 'D', 'L', 'f:sitemap_size'),
        ('Sitemap freshness', 'lastmod reflects real content changes, not the build date.', 'D', 'M', 'n:LIVE'),
        ('Sitemap submission', 'Sitemaps are submitted and read without errors in Search Console and Bing.', 'S', 'M', 'n:GSC'),
        ('Sitemap versus crawl', 'Every indexable page is in the sitemap, and every sitemap page is linked.', 'S', 'M', 'g:not-in-sitemap|orphans'),
        ('Broken internal links', 'No internal link points at a 4xx, 5xx or no-response URL.', 'W', 'H', 'g:broken|broken-res'),
        ('Server errors', 'No URL returns 5xx at normal crawl speed.', 'D', 'C', 'g:server-errors'),
        ('Soft 404s', 'Missing pages return a real 404 or 410, not a 200 error page.', 'D', 'M', 'g:soft404'),
        ('Custom 404 page', 'The 404 page returns status 404 and links back into the site.', 'D', 'M', 'n:LIVE'),
        ('Redirect type', 'Permanent moves use 301 or 308.', 'D', 'L', 'g:temp-redirects'),
        ('Redirect chains and loops', 'Every redirect resolves in one hop and none loop.', 'D', 'L', 'g:chains'),
        ('Internal links to redirects', 'Internal links point at final URLs, not redirects.', 'W', 'M', 'g:redirects'),
        ('Host consistency', 'http, www and trailing-slash variants all 301 to one version in one hop.', 'D', 'L', 'g:http-pages'),
        ('Old migration redirects', 'Old URLs that still have backlinks redirect to a live page.', 'S', 'M', 'n:LINKS'),
        ('Crawl stats', 'Crawl requests are steady and response times are low in the crawl stats report.', 'S', 'L', 'n:GSC'),
        ('Crawl waste', 'Bots spend little time on parameters, filters and duplicate paths.', 'D', 'M', 'n:LOGS'),
        ('Bot firewall', 'Search engine bots get 200, not a challenge or block page.', 'D', 'C', 'n:LIVE'),
        ('Staging and dev sites', 'Staging and dev hosts are password protected or noindexed.', 'D', 'H', 'n:LIVE'),
        ('IndexNow', 'IndexNow (or the Bing URL API) pings new and changed URLs.', 'D', 'L', 'n:BWT'),
        ('Log file checks', 'Key pages are crawled weekly; no wasted bot hits on junk URLs.', 'D', 'M', 'n:LOGS'),
    ]),
    ('2. Indexation', [
        ('Index coverage', 'The number of indexed pages matches the number you want indexed.', 'S', 'H', 'n:GSC'),
        ('Crawled, currently not indexed', 'Pages in this report are reviewed and improved, merged or removed.', 'S', 'M', 'n:GSC'),
        ('Discovered, currently not indexed', 'Pages in this report get internal links or are dropped.', 'S', 'M', 'n:GSC'),
        ('Index bloat', 'No parameter, duplicate or thin pages are indexable without a reason.', 'D', 'H', 'g:params|exact-dup'),
        ('Stray noindex', 'No page that should rank carries a noindex.', 'D', 'C', 'g:noindex-linked'),
        ('Noindex plus robots block', 'Pages you noindex are not also blocked in robots.txt (Google cannot see the noindex).', 'D', 'L', 'n:LIVE'),
        ('Canonical present', 'Every indexable page has a self-referencing absolute canonical.', 'D', 'H', 'g:canonicals'),
        ('Canonical target', 'No canonical points at a redirect, error or noindex page.', 'D', 'M', 'g:canonicals'),
        ('Canonical conflicts', 'Canonical, sitemap, internal links and hreflang all name the same URL.', 'D', 'M', 'g:canonicals|sitemap-bad'),
        ("Google's chosen canonical", 'URL Inspection shows Google picked your canonical.', 'S', 'M', 'n:GSC'),
        ('Canonical in raw HTML', 'The canonical is in the server HTML, not only added by JavaScript.', 'D', 'M', 'n:LIVE'),
        ('Parameter duplicates', 'Parameter URLs canonical to the clean URL.', 'D', 'M', 'g:params'),
        ('Case and slash duplicates', '/Page, /page and /page/ resolve to one URL.', 'D', 'L', 'g:url-hygiene'),
        ('Pagination', 'Paginated pages are indexable, self-canonical and linked with plain <a href> links.', 'D', 'L', 'n:MAN'),
        ('Exact duplicates', 'No two indexable URLs serve identical content.', 'W', 'M', 'g:exact-dup'),
        ('Near duplicates', 'Near-identical pages are merged or clearly different.', 'W', 'M', 'g:near-dup'),
        ('Duplicate titles and H1s', 'Every indexable page has its own title and H1.', 'W', 'M', 'g:titles|h1'),
        ('Manual actions', 'Search Console shows no manual action.', 'S', 'C', 'n:GSC'),
        ('Security issues', 'Search Console shows no security issue.', 'S', 'C', 'n:GSC'),
        ('Removals', 'No old removal request hides a page you now want indexed.', 'S', 'L', 'n:GSC'),
    ]),
    ('3. Site architecture and internal linking', [
        ('Click depth', 'Important pages are 3 clicks or fewer from the homepage.', 'S', 'M', 'g:deep'),
        ('Orphan pages', 'Every page you want indexed has at least one internal link.', 'W', 'M', 'g:orphans'),
        ('Inlink distribution', 'Money pages get the most internal links; no indexable page has fewer than 3.', 'S', 'M', 'g:few-inlinks'),
        ('Dead ends', 'Every page links onward to related content.', 'D', 'L', 'f:dead_ends'),
        ('Anchor text', 'Anchors describe the target page; no "click here".', 'W', 'M', 'g:generic-anchors'),
        ('Anchor conflicts', 'The same anchor does not point at two different pages.', 'W', 'M', 'f:anchor_conflicts'),
        ('Link format', 'Internal links are plain <a href> with https or relative URLs.', 'D', 'L', 'g:http-links'),
        ('Nofollow on internal links', 'Internal links to indexable pages are followed.', 'D', 'L', 'g:nofollow'),
        ('Navigation', 'The main menu links the key sections in crawlable HTML.', 'D', 'M', 'f:navigation'),
        ('Footer', 'The footer links trust and key pages without stuffing.', 'D', 'L', 'f:footer'),
        ('Breadcrumbs', 'Deep templates show breadcrumbs with BreadcrumbList markup.', 'D', 'M', 'f:schema:BreadcrumbList'),
        ('Contextual links', 'Body copy links to related pages, not only menus.', 'W', 'M', 'f:contextual'),
        ('Topic clusters', 'Each topic has a hub page that links to every page in the cluster and back.', 'W', 'M', 'n:MAN'),
        ('Related content modules', 'Posts and products show related items with real links.', 'D', 'L', 'n:MAN'),
        ('Links per page', 'Pages have a sensible number of links (under about 300).', 'D', 'L', 'f:links_per_page'),
        ('URL structure', 'URLs are short, lowercase, hyphenated and readable.', 'W', 'L', 'g:url-hygiene'),
        ('URL hierarchy', 'Folders reflect the site structure (/blog/post, /products/item).', 'D', 'L', 'f:hierarchy'),
        ('Subdomain versus subfolder', 'Content meant to rank sits in subfolders of the main host where possible.', 'D', 'M', 'f:subdomains'),
        ('HTML sitemap or hub pages', 'Large sections have a crawlable index or hub page.', 'D', 'L', 'n:MAN'),
    ]),
    ('4. Rendering and JavaScript', [
        ('Raw versus rendered HTML', 'Titles, canonicals, body text and links are in the server HTML.', 'D', 'H', 'n:LIVE'),
        ('Rendered output', 'URL Inspection shows the full page rendered.', 'S', 'M', 'n:GSC'),
        ('Blocked resources', 'No CSS or JS needed for rendering is blocked.', 'D', 'M', 'n:LIVE'),
        ('Rendering method', 'Pages that must rank are server-rendered or static.', 'D', 'M', 'n:MAN'),
        ('Lazy loaded content', 'Text and links do not wait for scrolling or clicks to load.', 'D', 'M', 'n:MAN'),
        ('Hidden content', 'Important text is not hidden behind tabs that load on click.', 'D', 'L', 'n:MAN'),
        ('Infinite scroll', 'Infinite lists also have paginated URLs with links.', 'D', 'M', 'n:MAN'),
        ('Client side routing', 'Each view has its own URL that loads directly.', 'D', 'M', 'n:MAN'),
        ('Fragment URLs', 'Content is not served only behind #fragments.', 'D', 'L', 'f:fragments'),
        ('JavaScript redirects', 'Redirects happen on the server, not in JavaScript.', 'D', 'L', 'n:LIVE'),
        ('Error states', 'Pages that fail to load data return an error status, not an empty 200.', 'D', 'M', 'g:soft404'),
        ('Hydration mismatches', 'The browser console shows no hydration errors on key templates.', 'D', 'L', 'n:MAN'),
        ('Cloaking', 'Bots and users get the same content.', 'D', 'C', 'n:LIVE'),
    ]),
    ('5. Performance and Core Web Vitals', [
        ('Field data by template', 'Each template passes LCP, INP and CLS in field data.', 'D', 'H', 'n:PSI'),
        ('Field data on money pages', 'Money pages pass Core Web Vitals on mobile.', 'D', 'H', 'n:PSI'),
        ('Server response time', 'Pages respond in under 0.8 s.', 'D', 'M', 'g:slow'),
        ('LCP element', 'The largest element is a fast, preloaded image or text.', 'D', 'M', 'n:PSI'),
        ('Hero images', 'Above-the-fold images are small, sized and not lazy-loaded.', 'D', 'M', 'g:heavy-img'),
        ('Render blocking resources', 'Only critical CSS blocks rendering; scripts are deferred.', 'D', 'M', 'n:PSI'),
        ('JavaScript weight', 'Each template ships as little JavaScript as it needs.', 'D', 'M', 'n:PSI'),
        ('Third party scripts', 'Tags, chat and widgets load late and are audited.', 'D', 'M', 'n:PSI'),
        ('Layout shift sources', 'Images, ads and embeds reserve their space.', 'D', 'M', 'n:PSI'),
        ('Fonts', 'Fonts are self-hosted or preloaded with font-display: swap.', 'D', 'L', 'n:PSI'),
        ('Image lazy loading', 'Below-the-fold images use loading="lazy".', 'D', 'L', 'n:LIVE'),
        ('Compression', 'Text responses use gzip or brotli.', 'D', 'M', 'g:compression'),
        ('Caching', 'Static files have long cache lifetimes.', 'D', 'L', 'g:asset-cache'),
        ('CDN and protocol', 'The site is served from a CDN over HTTP/2 or HTTP/3.', 'D', 'L', 'f:http_version'),
        ('Page weight', 'HTML is under 500 KB and images under 200 KB.', 'D', 'M', 'g:heavy-html|heavy-img'),
        ('Real user monitoring', 'Core Web Vitals are tracked from real users over time.', 'D', 'L', 'n:PSI'),
    ]),
    ('6. Mobile, security, and server health', [
        ('Mobile parity', 'Mobile shows the same content, links and structured data as desktop.', 'D', 'H', 'n:LIVE'),
        ('Viewport', 'Every page has a responsive viewport meta tag.', 'D', 'M', 'n:LIVE'),
        ('Tap targets', 'Buttons and links are big enough and spaced on mobile.', 'D', 'L', 'n:PSI'),
        ('Font size', 'Body text is readable without zooming.', 'D', 'L', 'n:PSI'),
        ('Interstitials', 'No pop-up covers the content on mobile landing.', 'D', 'M', 'n:MAN'),
        ('Mobile navigation', 'The mobile menu holds the same links as desktop, in the HTML.', 'D', 'M', 'n:MAN'),
        ('HTTPS', 'Every page is served over HTTPS.', 'D', 'C', 'f:https'),
        ('Mixed content', 'No http:// files load on https pages.', 'D', 'H', 'g:mixed'),
        ('HTTP to HTTPS', 'Every http URL 301s to https in one hop.', 'D', 'M', 'g:http-pages'),
        ('Security headers', 'HSTS, nosniff, frame and referrer headers are sent.', 'D', 'L', 'g:sec-headers'),
        ('Exposed files', '.env, .git, backups and admin paths are not public.', 'D', 'C', 'n:LIVE'),
        ('Hacked content', 'No injected spam pages or links.', 'S', 'C', 'n:GSC'),
        ('Uptime', 'The site is monitored and up more than 99.9% of the time.', 'D', 'M', 'n:LOGS'),
        ('Accessibility basics', 'Images have alt text, headings are in order, contrast is readable.', 'W', 'M', 'g:alt|h1'),
    ]),
    ('7. On page elements', [
        ('Title present and unique', 'Every indexable page has its own title.', 'W', 'H', 'g:titles'),
        ('Title length', 'Titles are about 30 to 60 characters.', 'W', 'L', 'g:titles'),
        ('Title content', 'The main topic comes first, the brand last.', 'W', 'M', 'n:MAN'),
        ('Title rewrites', 'Google mostly shows your titles as written.', 'S', 'L', 'n:GSC'),
        ('Meta description', 'Each page has a unique description of 70 to 160 characters.', 'W', 'L', 'g:meta'),
        ('H1', 'Exactly one H1 per page, unique across the site.', 'W', 'M', 'g:h1'),
        ('Heading hierarchy', 'Long pages are broken up with H2 and H3 headings.', 'W', 'L', 'g:h2'),
        ('Keyword in opening', 'The main topic is clear in the first 100 words.', 'W', 'L', 'n:MAN'),
        ('Keyword mapping', 'Each target keyword has one page that owns it.', 'S', 'M', 'n:RANK'),
        ('URL slug', 'Slugs are short and say what the page is about.', 'W', 'L', 'g:url-hygiene'),
        ('Image alt text', 'Content images have descriptive alt text.', 'W', 'M', 'g:alt'),
        ('Image files', 'Images are compressed, modern formats with sensible file names.', 'D', 'L', 'g:heavy-img'),
        ('Open Graph and X card tags', 'Pages have og:title, og:description, og:image and a twitter:card.', 'D', 'M', 'n:LIVE'),
        ('Outbound links', 'External links work and point at trusted sources.', 'W', 'L', 'g:broken-ext'),
        ('Publish and update dates', 'Articles show a visible date that matches the markup.', 'D', 'L', 'n:MAN'),
        ('Calls to action', 'Each page has one clear next step.', 'W', 'M', 'n:MAN'),
        ('Favicon and site name', 'A favicon and WebSite name markup are set so results show your brand.', 'D', 'L', 'f:schema:WebSite'),
    ]),
    ('8. Content', [
        ('Search intent match', 'Each page matches what the top results for its keyword deliver.', 'S', 'H', 'n:RANK'),
        ('Cannibalization', 'No two pages swap rankings for the same query.', 'S', 'M', 'n:GSC'),
        ('Thin content', 'Pages that should rank have enough useful detail.', 'W', 'L', 'g:thin'),
        ('Zero traffic pages', 'Pages with no clicks in 12 months are improved, merged or removed.', 'W', 'M', 'n:GSC'),
        ('Content decay', 'Pages losing clicks year over year are refreshed.', 'S', 'M', 'n:GSC'),
        ('Freshness', 'Time-sensitive pages are reviewed on a schedule.', 'W', 'L', 'n:MAN'),
        ('Striking distance keywords', 'Queries in positions 5 to 20 are pushed with updates and links.', 'S', 'M', 'n:GSC'),
        ('Low click rate at high rank', 'Pages ranking top 5 with a low click rate get better titles.', 'S', 'M', 'n:GSC'),
        ('Topical coverage', 'The site covers the subtopics buyers search for.', 'W', 'M', 'n:MAN'),
        ('Keyword gaps', 'Keywords competitors rank for are mapped to pages.', 'S', 'M', 'n:LINKS'),
        ('Funnel coverage', 'There are pages for learning, comparing and buying.', 'S', 'M', 'n:MAN'),
        ('Commercial pages', 'Product, pricing and comparison pages are indexable and linked.', 'S', 'H', 'f:commercial'),
        ('Originality', 'Pages add something not found in the top results.', 'W', 'M', 'n:MAN'),
        ('Scaled low value content', 'No mass-produced pages with little unique value.', 'W', 'H', 'g:near-dup|thin'),
        ('Readability', 'Short paragraphs, plain words, scannable lists.', 'W', 'L', 'f:readability'),
        ('Accuracy', 'Facts, prices and screenshots are current.', 'W', 'M', 'n:MAN'),
        ('Media', 'Pages use original images, diagrams or video where they help.', 'W', 'L', 'n:MAN'),
        ('Duplicate and syndicated copies', 'Copies on other sites canonical to you or are noindexed.', 'S', 'L', 'n:MAN'),
        ('Outdated pages', 'Old years and expired offers are updated or removed.', 'W', 'L', 'f:outdated'),
    ]),
    ('9. Structured data and search features', [
        ('Format', 'Structured data uses JSON-LD.', 'D', 'L', 'f:schema_any'),
        ('Validity', 'Structured data has no errors.', 'D', 'H', 'g:sd-errors'),
        ('Match to visible content', 'Marked-up facts appear on the page.', 'D', 'M', 'n:MAN'),
        ('Organization', 'The homepage has Organization markup with logo and sameAs.', 'D', 'M', 'f:schema:Organization'),
        ('WebSite', 'The homepage has WebSite markup with the site name.', 'D', 'L', 'f:schema:WebSite'),
        ('BreadcrumbList', 'Deep templates have BreadcrumbList markup.', 'D', 'M', 'f:schema:BreadcrumbList'),
        ('Article or BlogPosting', 'Posts have Article markup with author and dates.', 'D', 'M', 'f:schema:Article|BlogPosting|NewsArticle'),
        ('Person', 'Authors have Person markup on their pages.', 'D', 'L', 'f:schema:Person'),
        ('SoftwareApplication or Product', 'Product pages have Product or SoftwareApplication markup.', 'D', 'M', 'f:schema:Product|SoftwareApplication'),
        ('Review and rating markup', 'Ratings are marked up only where real reviews are shown.', 'D', 'L', 'n:MAN'),
        ('VideoObject', 'Pages with video have VideoObject markup.', 'D', 'L', 'n:MAN'),
        ('Retired types', 'No effort spent on rich result types Google retired or limited.', 'D', 'L', 'f:retired'),
        ('Search Console enhancements', 'Enhancement reports show valid items, no errors.', 'S', 'M', 'n:GSC'),
        ('Result features owned', 'You know which snippets, panels and carousels you show in.', 'S', 'L', 'n:RANK'),
        ('Featured snippet targets', 'Question pages answer in the first lines, with lists or tables.', 'W', 'L', 'n:MAN'),
        ('Image and video search', 'Images and video get clicks from image and video search.', 'S', 'L', 'n:GSC'),
    ]),
    ('10. International and multilingual', [
        ('hreflang present', 'Sites with more than one language or region use hreflang.', 'D', 'H', 'f:hreflang_present'),
        ('hreflang return tags', 'Every alternate links back to the page that lists it.', 'D', 'H', 'g:hreflang'),
        ('hreflang self-reference', 'Each page lists itself in its hreflang set.', 'D', 'M', 'g:hreflang'),
        ('hreflang targets', 'Every hreflang URL is live, indexable and canonical.', 'D', 'M', 'g:hreflang'),
        ('x-default', 'An x-default points at the fallback page.', 'D', 'L', 'f:xdefault'),
        ('Language codes', 'Codes are valid ISO 639-1 (plus optional ISO 3166 region).', 'D', 'M', 'f:lang_codes'),
        ('Language versions are translated', 'Each language version is translated, not a copy with a new URL.', 'W', 'M', 'n:MAN'),
    ]),
    ('11. Off page and backlinks', [
        ('Referring domains trend', 'Referring domains grow or hold over 12 months.', 'S', 'M', 'n:LINKS'),
        ('Gap to competitors', 'You know which sites link to competitors and not to you.', 'S', 'M', 'n:LINKS'),
        ('Link quality', 'Most links come from relevant sites with real traffic.', 'S', 'M', 'n:LINKS'),
        ('Link distribution', 'Money pages earn links, not only the homepage.', 'S', 'M', 'n:LINKS'),
        ('Anchor text profile', 'Anchors are mostly brand and natural phrases.', 'S', 'L', 'n:LINKS'),
        ('Lost links', 'Lost links are reviewed monthly and recovered where possible.', 'S', 'L', 'n:LINKS'),
        ('Broken backlinks', 'URLs with backlinks that now 404 are redirected.', 'S', 'H', 'n:LINKS'),
        ('Link velocity', 'New links arrive steadily, without odd spikes.', 'S', 'L', 'n:LINKS'),
        ('Risky links', 'No paid, sitewide or link-scheme links that break guidelines.', 'S', 'M', 'n:LINKS'),
        ('Disavow file', 'The disavow file is current or not needed.', 'S', 'L', 'n:GSC'),
        ('Unlinked brand mentions', 'Mentions of the brand without a link are asked for one.', 'S', 'L', 'n:LINKS'),
        ('Best-of lists and roundups', 'You appear in the "best X" lists buyers read.', 'S', 'M', 'n:MAN'),
        ('Digital PR assets', 'You have data, tools or studies people link to.', 'S', 'M', 'n:MAN'),
        ('Review platforms', 'Profiles on the review sites in your market are claimed and active.', 'S', 'M', 'n:MAN'),
        ('Community presence', 'The brand is discussed helpfully in forums and communities.', 'S', 'L', 'n:MAN'),
        ('Competitor link sources', 'Sources that link to several competitors are on your outreach list.', 'S', 'L', 'n:LINKS'),
    ]),
    ('12. Trust and entity signals', [
        ('Author bylines', 'Articles name a real author.', 'W', 'M', 'n:MAN'),
        ('Author pages', 'Each author has a page with bio, credentials and links.', 'W', 'M', 'f:author_pages'),
        ('First hand experience', 'Content shows real use: own photos, data, results.', 'W', 'M', 'n:MAN'),
        ('About page', 'An About page explains who runs the site.', 'W', 'M', 'f:trust:about'),
        ('Contact and support', 'A contact page with a real way to reach you.', 'W', 'M', 'f:trust:contact'),
        ('Policies', 'Privacy and terms pages exist and are linked.', 'W', 'L', 'f:trust:privacy|terms'),
        ('Social proof', 'Reviews, logos and case studies are shown with sources.', 'S', 'L', 'n:MAN'),
        ('Brand search results', 'A search for the brand shows your own pages and profiles first.', 'S', 'M', 'n:MAN'),
        ('Knowledge panel', 'The brand has a correct knowledge panel, or is working toward one.', 'S', 'L', 'n:MAN'),
        ('Entity consistency', 'Name, logo and description match on the site and every profile.', 'S', 'L', 'n:MAN'),
        ('Profile links in schema', 'Organization sameAs lists every official profile.', 'D', 'L', 'f:schema:Organization'),
        ('Third party profiles', 'Business directories and marketplaces list the brand correctly.', 'S', 'L', 'n:MAN'),
        ('Brand search demand', 'Branded searches grow over time.', 'S', 'L', 'n:GSC'),
        ('Reputation risks', 'Searches for brand + reviews / complaints show no unanswered problems.', 'S', 'M', 'n:MAN'),
        ('Ads and affiliate disclosure', 'Paid and affiliate links are labelled and use rel="sponsored".', 'S', 'M', 'n:MAN'),
    ]),
    ('13. AI search visibility', [
        ('AI crawler access', 'AI search crawlers you want (OAI-SearchBot, PerplexityBot, Claude-SearchBot, Bingbot) get 200.', 'D', 'H', 'n:LIVE'),
        ('Training versus search agents', 'robots.txt states a deliberate choice for training and search agents.', 'S', 'L', 'n:LIVE'),
        ('Firewall and CDN rules', 'Bot protection does not block AI crawlers you allow in robots.txt.', 'D', 'H', 'n:LIVE'),
        ('AI bot activity', 'Logs show AI crawlers fetching key pages with 200s.', 'D', 'L', 'n:LOGS'),
        ('Content without JavaScript', 'Key facts and text are in the server HTML (most AI crawlers do not run JS).', 'D', 'H', 'n:LIVE'),
        ('Google AI opt out', 'No snippet controls hide pages from AI answers by accident.', 'S', 'L', 'n:LIVE'),
        ('AI impressions', 'AI answer impressions are tracked where the platform reports them.', 'S', 'L', 'n:GSC'),
        ('Prompt set', 'A fixed list of buyer prompts is tested every month.', 'S', 'M', 'n:AI'),
        ('Mention rate and position', 'You know how often and how high the brand appears in AI answers.', 'S', 'M', 'n:AI'),
        ('Share of voice', 'Your mentions are compared with competitors.', 'S', 'L', 'n:AI'),
        ('Accuracy', 'AI answers describe your product, prices and features correctly.', 'S', 'M', 'n:AI'),
        ('Sentiment', 'AI answers describe the brand fairly.', 'S', 'L', 'n:AI'),
        ('Cited sources', 'You know which pages AI engines cite, yours and others.', 'W', 'M', 'n:AI'),
        ('Answer ready content', 'Pages answer the question directly in the first lines.', 'W', 'M', 'n:MAN'),
        ('Extractable structure', 'Question headings, short lists and tables make answers easy to quote.', 'W', 'M', 'g:h2'),
        ('Original facts', 'Pages hold numbers, data or quotes found nowhere else.', 'W', 'M', 'n:MAN'),
        ('Comparison and alternative pages', 'You have honest "X vs Y" and "alternatives" pages.', 'W', 'M', 'f:comparison'),
        ('Machine readable product facts', 'Pricing, features and integrations are public, crawlable text.', 'S', 'M', 'n:MAN'),
        ('AI referral traffic', 'Visits from AI assistants show as their own channel.', 'S', 'L', 'n:GA'),
        ('Bing index', 'Key pages are indexed in Bing (many AI tools search with it).', 'S', 'M', 'n:BWT'),
        ('llms.txt (optional)', 'An llms.txt lists key pages, if you choose to publish one.', 'D', 'L', 'n:LIVE'),
    ]),
    ('14. Measurement and tracking', [
        ('Search Console setup', 'A domain property is verified with the right users.', 'S', 'H', 'n:GSC'),
        ('Bing Webmaster Tools', 'The site is verified in Bing Webmaster Tools.', 'S', 'L', 'n:BWT'),
        ('Analytics coverage', 'The analytics tag fires once on every template.', 'D', 'M', 'n:GA'),
        ('Channel definition', 'Organic, AI assistants, referral and direct are separate channels.', 'S', 'M', 'n:GA'),
        ('Conversion events', 'Sign-ups, demos and purchases are tracked by landing page.', 'S', 'H', 'n:GA'),
        ('Landing page to revenue path', 'You can see revenue by organic landing page.', 'S', 'M', 'n:GA'),
        ('Cross domain tracking', 'Sessions survive moves between your domains (site to app or shop).', 'D', 'M', 'n:GA'),
        ('Consent handling', 'Tracking respects consent and still records what it may.', 'D', 'M', 'n:GA'),
        ('Internal traffic', 'Staff and bot traffic are filtered out.', 'S', 'L', 'n:GA'),
        ('Campaign parameters', 'No UTM tags on internal links.', 'W', 'M', 'g:utm'),
        ('Rank tracking', 'Money keywords are tracked by device and country.', 'S', 'M', 'n:RANK'),
        ('Branded versus non branded', 'Brand and non-brand clicks are reported separately.', 'S', 'L', 'n:GSC'),
        ('Annotations', 'Releases, migrations and algorithm updates are noted on charts.', 'S', 'L', 'n:MAN'),
        ('Alerts', 'Alerts fire on traffic drops, index drops, 5xx spikes and robots.txt changes.', 'S', 'M', 'n:MAN'),
        ('Baseline snapshot', 'A dated baseline exists to compare the next audit with.', 'S', 'M', 'f:baseline'),
    ]),
    ('15. Competitor benchmark', [
        ('Organic footprint', 'You know competitors\' organic traffic and keyword counts.', 'S', 'L', 'n:COMP'),
        ('Keyword overlap and gaps', 'Shared and missing keywords are listed.', 'S', 'M', 'n:COMP'),
        ('Top pages', 'You know which competitor pages bring them the most traffic.', 'S', 'L', 'n:COMP'),
        ('Page type coverage', 'You have the page types competitors win with.', 'S', 'M', 'n:COMP'),
        ('Content depth and cadence', 'Your depth and publishing pace compare well.', 'S', 'L', 'n:COMP'),
        ('Link profile', 'Referring domains compare well.', 'S', 'L', 'n:COMP'),
        ('Technical quality', 'Competitors\' technical issues and speed are known.', 'S', 'L', 'n:COMP'),
        ('Result features held', 'You know which search features competitors hold.', 'S', 'L', 'n:COMP'),
        ('AI visibility', 'Competitors\' AI answer presence is compared with yours.', 'S', 'L', 'n:COMP'),
        ('Brand strength', 'Branded search demand is compared.', 'S', 'L', 'n:COMP'),
    ]),
    ('16. Prioritizing and reporting the findings', [
        ('Ranked fix list', 'Findings are ranked by impact and effort with an owner.', 'S', 'M', 'f:ranked'),
        ('Seven fields per finding', 'Each finding has issue, evidence, why, fix, priority, owner and a done-when line.', 'S', 'L', 'f:ranked'),
        ('Re-crawl after fixes', 'A new crawl confirms each fix.', 'S', 'M', 'f:baseline'),
    ]),
]


def count():
    return sum(len(items) for _, items in SECTIONS)


class Evaluator:
    def __init__(self, crawl, groups, has_previous=False):
        self.c = crawl
        self.g = {g['id']: g for g in groups}
        self.prev = has_previous

    def from_groups(self, ids):
        gs = [self.g[i] for i in ids if i in self.g]
        open_ = [g for g in gs if g['status'] == 'open']
        skipped = [g for g in gs if g['status'] == 'skip']
        if open_:
            ev = ' '.join(g['summary'] for g in open_)
            return ('fail' if any(g['sev'] == 'bad' for g in open_) else 'warn'), ev, open_[0]['id']
        if skipped and len(skipped) == len(gs):
            return 'todo', skipped[0]['summary'], ''
        return 'pass', 'No problems found in the crawl.', ''

    def run(self):
        out, counts = [], Counter()
        for title, items in SECTIONS:
            sec = {'t': title, 'items': []}
            for name, what, owner, sev, how in items:
                kind, _, arg = how.partition(':')
                gid = ''
                if kind == 'g':
                    st, ev, gid = self.from_groups(arg.split('|'))
                elif kind == 'n':
                    st, ev = 'todo', NEEDS[arg] + '.'
                else:
                    st, ev = self.fn(arg)
                counts[st] += 1
                sec['items'].append({'c': name, 'what': what, 's': st, 'e': ev, 'o': OWNER[owner],
                                     'v': SEV[sev] if st in ('fail', 'warn') else '', 'g': gid})
            out.append(sec)
        return {'sections': out, 'counts': dict(counts), 'total': sum(counts.values())}

    # ---------- small checks answered from the crawl ----------
    def fn(self, arg):
        c = self.c
        name, _, param = arg.partition(':')
        idx = c.indexable
        if name == 'schema':
            if not c.have['structured']:
                return 'todo', 'Not checked: export "Structured Data:All".'
            types = param.split('|')
            n = sum(1 for r in idx if any(t in c.schema.get(r['Address'], {}).get('types', []) for t in types))
            return ('pass', f'{param.replace("|", " / ")} markup found on {n:,} pages.') if n else ('warn', f'No {param.replace("|", " or ")} markup found on any indexable page.')
        if name == 'schema_any':
            if not c.have['structured']:
                return 'todo', 'Not checked: export "Structured Data:All".'
            n = sum(1 for r in idx if c.schema.get(r['Address'], {}).get('types'))
            return ('pass' if n else 'warn'), f'{n:,} of {len(idx):,} indexable pages carry structured data.'
        if name == 'retired':
            if not c.have['structured']:
                return 'todo', 'Not checked: export "Structured Data:All".'
            n = sum(1 for r in idx if {'HowTo', 'FAQPage'} & set(c.schema.get(r['Address'], {}).get('types', [])))
            return ('warn', f'{n:,} pages use HowTo or FAQPage, which Google no longer shows (or shows only for a few sites) as rich results. Harmless, but not worth more effort.') if n else ('pass', 'No retired rich result types found.')
        if name == 'sitemap_size':
            if c.sitemap_urls is None:
                return 'todo', 'Not checked: no sitemap given.'
            n = len(c.sitemap_urls)
            return ('pass' if n <= 50000 else 'warn'), f'{n:,} URLs in the sitemap set.'
        if name == 'https':
            http = [r for r in c.live if r['Address'].startswith('http://')]
            return ('fail', f'{len(http):,} pages load over http://.') if http else ('pass', f'All {len(c.live):,} live HTML pages are on https.')
        if name == 'http_version':
            if not c.has_col('HTTP Version'):
                return 'todo', 'Not checked: no "HTTP Version" column.'
            v = Counter(r.get('HTTP Version', '') for r in c.live).most_common(1)
            v = v[0][0] if v else ''
            return ('pass' if v.startswith(('2', '3')) else 'warn'), f'Most pages were served over HTTP/{v or "?"} (the crawler may not use HTTP/3 even when the server offers it).'
        if name == 'dead_ends':
            if not c.has_col('Unique Outlinks'):
                return 'todo', 'Not checked: no "Unique Outlinks" column.'
            n = [r for r in idx if to_int(r.get('Unique Outlinks')) == 0]
            return ('warn' if n else 'pass'), f'{len(n):,} indexable pages link to no other page.'
        if name == 'links_per_page':
            if not c.has_col('Unique Outlinks'):
                return 'todo', 'Not checked: no "Unique Outlinks" column.'
            n = [r for r in idx if to_int(r.get('Unique Outlinks')) > 300]
            return ('warn' if n else 'pass'), f'{len(n):,} pages have more than 300 unique links.'
        if name in ('navigation', 'footer', 'contextual'):
            if not c.links:
                return 'todo', 'Not checked: needs all_inlinks.csv.'
            pos = {'navigation': ('Navigation', 'Header'), 'footer': ('Footer',), 'contextual': ('Content',)}[name]
            srcs = {l.src for l in c.links if l.type == 'Hyperlink' and l.pos in pos and c.own(l.dst)}
            share = len(srcs) / max(1, len(c.live))
            ok = share > (0.5 if name != 'contextual' else 0.3)
            return ('pass' if ok else 'warn'), f'{len(srcs):,} of {len(c.live):,} live pages have {pos[0].lower()} links to the site.'
        if name == 'anchor_conflicts':
            if not c.links:
                return 'todo', 'Not checked: needs all_inlinks.csv.'
            m = {}
            for l in c.links:
                if l.type == 'Hyperlink' and l.pos == 'Content' and c.own(l.dst) and len(l.text) > 3 and l.text.lower() not in ('home', 'blog'):
                    m.setdefault(l.text.lower(), set()).add(l.dst.rstrip('/'))
            bad = sorted((k for k, v in m.items() if len(v) > 1), key=lambda k: -len(m[k]))
            return ('warn', f'{len(bad):,} anchors point at more than one URL, e.g. "{bad[0]}".') if bad else ('pass', 'Each in-content anchor points at one URL.')
        if name == 'hierarchy':
            flat = [r for r in idx if urlsplit(r['Address']).path.count('/') <= 1]
            return 'pass', f'{len(idx) - len(flat):,} indexable pages sit in a folder, {len(flat):,} at the root.'
        if name == 'subdomains':
            subs = Counter(urlsplit(r['Address']).netloc for r in idx if not c.on_main(r['Address']))
            return ('warn', 'Indexable pages on subdomains: ' + ', '.join(f'{h} ({n:,})' for h, n in subs.most_common(5)) + '.') if subs else ('pass', 'All indexable pages are on the main host.')
        if name == 'fragments':
            n = [l for l in c.links if l.type == 'Hyperlink' and '#!' in l.dst]
            return ('warn', f'{len(n):,} links use #! fragment routes.') if n else ('pass', 'No #! fragment routes found in links.')
        if name == 'commercial':
            words = ('pricing', 'product', 'products', 'features', 'compare', 'vs', 'shop', 'buy', 'plans')
            n = [r['Address'] for r in idx if any(w in re.split(r'[/\-]', urlsplit(r['Address']).path.lower()) for w in words)]
            return ('pass', f'{len(n):,} indexable commercial pages found (pricing, product, compare, shop).') if n else ('todo', 'No URL looked commercial by name. Check by hand.')
        if name == 'comparison':
            n = [r for r in idx if re.search(r'(-vs-|/vs/|alternative|compare)', r['Address'].lower())]
            return ('pass', f'{len(n):,} comparison or alternatives pages found.') if n else ('todo', 'No comparison or alternatives page found by URL. Check by hand.')
        if name == 'readability':
            if not c.has_col('Flesch Reading Ease Score'):
                return 'todo', 'Not checked: no readability column (Config > Content > readability).'
            hard = [r for r in idx if 0 < to_int(r.get('Flesch Reading Ease Score')) < 30]
            return ('warn' if hard else 'pass'), f'{len(hard):,} indexable pages score under 30 on Flesch reading ease (hard to read).'
        if name == 'outdated':
            yrs = [r for r in idx if re.search(r'\b(20[01]\d|202[0-3])\b', (r.get('Title 1') or ''))]
            return ('warn', f'{len(yrs):,} titles mention a year from 2023 or earlier.') if yrs else ('pass', 'No titles mention an old year.')
        if name == 'author_pages':
            n = [r for r in idx if re.search(r'/(author|authors|team|people)/', r['Address'])]
            return ('pass', f'{len(n):,} author pages found.') if n else ('todo', 'No author pages found by URL. Check by hand.')
        if name == 'trust':
            words = param.split('|')
            found = {w: any(w in r['Address'].lower() for r in c.live) for w in words}
            miss = [w for w, ok in found.items() if not ok]
            return ('warn', 'Not found in the crawl: ' + ', '.join(miss) + ' page.') if miss else ('pass', 'Found: ' + ', '.join(words) + ' page.')
        if name == 'hreflang_present':
            if not c.have['hreflang']:
                return 'todo', 'Not checked: export "Hreflang:All".'
            return ('pass', f'hreflang found on {len(c.hreflang):,} pages.') if c.hreflang else ('na', 'No hreflang tags found. Skip this section if the site has one language and one market.')
        if name == 'xdefault':
            if not c.hreflang:
                return 'na', 'No hreflang tags found.'
            n = sum(1 for tags in c.hreflang.values() if any(l == 'x-default' for l, _ in tags))
            return ('pass' if n == len(c.hreflang) else 'warn'), f'x-default on {n:,} of {len(c.hreflang):,} pages with hreflang.'
        if name == 'lang_codes':
            if not c.hreflang:
                return 'na', 'No hreflang tags found.'
            bad = {l for tags in c.hreflang.values() for l, _ in tags if l != 'x-default' and not re.match(r'^[a-z]{2}(-[A-Za-z]{2}|-[0-9]{3})?$', l)}
            return ('warn', 'Invalid codes: ' + ', '.join(sorted(bad))) if bad else ('pass', 'All hreflang codes are valid.')
        if name == 'baseline':
            return ('pass', 'This report compares with a previous crawl.') if self.prev else ('warn', 'Keep this crawl folder and run the next audit with --previous to compare.')
        if name == 'ranked':
            return 'pass', 'The Audit tab ranks every open issue by priority, with owner, fix and a done-when line.'
        return 'todo', NEEDS['MAN'] + '.'
