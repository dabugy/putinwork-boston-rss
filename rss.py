from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
import re
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

SOURCE = 'https://putinworktv.com/boston/'
OUTPUT = Path('feed.xml')
DATE = re.compile(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b')


def scrape(html):
    soup = BeautifulSoup(html, 'html.parser')
    articles = []
    seen = set()

    for heading in soup.select('h3'):
        a = heading.find('a', href=True)
        if not a:
            continue
        url = urljoin(SOURCE, a['href']).split('#')[0]
        title = a.get_text(' ', strip=True)
        if not title or url in seen or urlparse(url).netloc not in ('putinworktv.com', 'www.putinworktv.com'):
            continue

        # Try to find the date near the headline, without reading unrelated articles.
        date = None
        for node in (heading.parent, heading.parent.parent if heading.parent else None):
            if node is None:
                continue
            value = node.get_text(' ', strip=True)
            if len(value) > 600:
                continue
            match = DATE.search(value)
            if match:
                date = datetime.strptime(match.group(), '%B %d, %Y').replace(tzinfo=timezone.utc)
                break
        articles.append((url, title, date))
        seen.add(url)
    return articles


def existing():
    if not OUTPUT.exists():
        return []
    root = ET.parse(OUTPUT).getroot()
    items = []
    for item in root.findall('./channel/item'):
        url = item.findtext('link')
        title = item.findtext('title')
        date = item.findtext('pubDate')
        if url and title:
            items.append((url, title, date))
    return items


def build(articles, old):
    # Reuse existing publication dates when a listing does not provide one.
    saved = {url: (title, date) for url, title, date in old}
    current = []
    seen = set()
    for url, title, date in articles:
        previous_date = saved.get(url, ('', None))[1]
        current.append((url, title, format_datetime(date) if date else previous_date))
        seen.add(url)
    for url, title, date in old:
        if url not in seen:
            current.append((url, title, date))
            seen.add(url)
    return current[:100]


def write(items):
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    for tag, value in (
        ('title', 'PUTINWORKTV — Boston News'),
        ('link', SOURCE),
        ('description', 'New articles from PUTINWORKTV Boston.'),
        ('language', 'en-us'),
    ):
        ET.SubElement(channel, tag).text = value
    for url, title, date in items:
        item = ET.SubElement(channel, 'item')
        for tag, value in (('title', title), ('link', url), ('guid', url)):
            element = ET.SubElement(item, tag)
            element.text = value
            if tag == 'guid':
                element.set('isPermaLink', 'true')
        if date:
            ET.SubElement(item, 'pubDate').text = date
    ET.indent(rss, space='  ')
    content = ET.tostring(rss, encoding='utf-8', xml_declaration=True)
    if not OUTPUT.exists() or OUTPUT.read_bytes() != content:
        OUTPUT.write_bytes(content)
        print(f'Updated feed.xml with {len(items)} articles')
    else:
        print('No changes to feed.xml')


def main():
    response = requests.get(SOURCE, timeout=30, headers={'User-Agent': 'Mozilla/5.0 (compatible; BostonRSS/1.0)'})
    response.raise_for_status()
    articles = scrape(response.text)
    if not articles:
        raise RuntimeError('No article headlines found; refusing to overwrite feed.xml')
    print(f'Found {len(articles)} articles on Boston page')
    write(build(articles, existing()))


if __name__ == '__main__':
    main()
