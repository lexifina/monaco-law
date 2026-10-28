"""Builds a git history of Monaco law from Legimonaco, in which every amending law is one commit, dated the day it took
effect.

    python -X utf8 scripts/monaco-law/build.py [--repo ../monaco-law] [--today 2026-10-28] [--offline] [--verify-rebuild]

Legimonaco (https://legimonaco.mc), the official legal database of the Principality, publishes every consolidated
version of a text under its own address, `<text>@YYYY.MM.DD/`, dated the day that version applies from, and lists the
versions at `<text>?versions`. Each article of each version carries a "Historique de consolidation" naming the laws
that created, amended or repealed it. We take every version of the acts below, compare consecutive versions article by
article, and credit each change to the law that the newer version's history of that article adds. Nothing is credited
by guesswork: a change no law explains is committed apart, by the publisher, and labelled as such.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

from lxml import html as lhtml

from reproduce import write_manifest, write_reproduce

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = HERE / '.cache'
BASE = 'https://legimonaco.mc'
USER_AGENT = 'lexifina-watch/1.0 (+https://lexifina.com; corpus@lexifina.com)'
THROTTLE = 1.0   # seconds between requests to Legimonaco
COMMITTER = ('Lexifina', 'monaco-law@lexifina.com')
PUBLISHER = ('Legimonaco', 'legimonaco@legimonaco.invalid')

# The acts in the record: Legimonaco's address of the text, a folder name, and how the act itself is named as the
# author of its original text.
ACTS = [
    {'path': '/constitution', 'slug': 'constitution', 'short': 'Constitution',
     'author': ('Constitution du 17 décembre 1962', 'constitution-1962@legimonaco.invalid'), 'enacted': '1962-12-17'},
    {'path': '/tnc/loi/2009/08-03-1.362', 'slug': 'loi-1362', 'short': 'Loi n° 1.362',
     'author': ('Loi n° 1.362 du 3 août 2009', 'loi-1362@legimonaco.invalid'), 'enacted': '2009-08-03'},
]


# ---------------------------------------------------------------- fetching

REQUESTS: list[dict] = []   # every request the build made, for REPRODUCE.md
_last = [0.0]


def _download(url: str) -> bytes:
    """One polite request: urllib first, curl if the machine's certificate store rejects the chain."""
    wait = THROTTLE - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except urllib.error.URLError as e:
        if 'CERTIFICATE' not in str(e).upper():
            raise
    out = subprocess.run(['curl', '-sSfL', '--max-time', '120', '-A', USER_AGENT, url], capture_output=True)
    if out.returncode:
        raise OSError(f'curl {url}: {out.stderr.decode(errors="replace")}')
    return out.stdout


def fetch(url: str, offline: bool = False) -> bytes:
    """GET with a file cache keyed by the URL, so a rebuild reads the same bytes."""
    path = CACHE / hashlib.sha256(url.encode()).hexdigest()[:32]
    REQUESTS.append({'url': url, 'file': path})
    if path.exists():
        return path.read_bytes()
    if offline:
        raise SystemExit(f'not cached: {url}')
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / '.gitignore').write_text('*\n')
    for attempt in range(4):
        try:
            body = _download(url)
            path.write_bytes(body)
            return body
        except Exception:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError


def versions_url(act: dict) -> str:
    return f'{BASE}{act["path"]}?versions'


def version_url(act: dict, day: str) -> str:
    return f'{BASE}{act["path"]}@{day.replace("-", ".")}/'


def version_days(act: dict, offline: bool) -> list[str]:
    """Every consolidated version Legimonaco lists, oldest first, as ISO days."""
    v = json.loads(fetch(versions_url(act), offline))
    days = v.get('previousVersions', []) + [v['currentVersion']] + v.get('nextVersions', [])
    return sorted(d.replace('.', '-') for d in days)


# ---------------------------------------------------------------- reading a version

def clean(s: str) -> str:
    """Spacing normalised and invisible characters dropped. Nothing else about the words is changed."""
    s = ''.join(ch for ch in s if unicodedata.category(ch) not in ('Cf', 'Cc') or ch == '\n')
    return re.sub(r'\s+', ' ', s.replace(' ', ' ')).strip()


def classes(e) -> set:
    return set((e.get('class') or '').split()) if isinstance(e.tag, str) else set()


def words_of(e) -> str:
    """The words of an element, without editorial note markers."""
    def walk(x) -> str:
        if not isinstance(x.tag, str):
            return ''
        if classes(x) & {'note', 'tooltip_ref', 'editoNote_ref', 'tooltip_a', 'noIndex'} or x.tag in ('script', 'style'):
            return ''
        acc = x.text or ''
        for c in x:
            acc += walk(c) + (c.tail or '')
        if x.tag == 'br':
            acc = ' ' + acc
        return acc
    return walk(e)


def lines_of(text_div) -> list[dict]:
    """An article's body as lines: each paragraph and each list item is one line, at the depth of its list."""
    out: list[dict] = []

    def emit(s: str, level: int):
        t = clean(s)
        if t:
            out.append({'level': level, 'text': t})

    def walk(x, level: int):
        if not isinstance(x.tag, str):
            return
        if x.tag in ('ul', 'ol'):
            for li in x:
                walk(li, level + 1)
            return
        if x.tag == 'table':
            for tr in x.iter('tr'):
                emit(' | '.join(clean(words_of(td)) for td in tr if isinstance(td.tag, str)), level)
            return
        blocks = [c for c in x if isinstance(c.tag, str) and c.tag in ('p', 'ul', 'ol', 'table', 'div', 'li', 'blockquote')]
        if x.tag in ('p', 'li', 'div', 'blockquote') and not blocks:
            emit(words_of(x), level)
            return
        # Text with blocks inside it: the words around each block are lines of their own, in document order.
        buf = x.text or ''
        for c in x:
            if c in blocks:
                emit(buf, level)
                walk(c, level)
                buf = c.tail or ''
            else:
                buf += words_of(c) + (c.tail or '')
        emit(buf, level)

    for c in text_div:
        walk(c, 0)
    return out


def histo_clauses(aside) -> list[dict]:
    """The acts a "Historique de consolidation" names, in order, each with the day its clause gives ("modifié à compter
    du 30 septembre 2023 par la loi n° ...") and a group number shared by acts named jointly in one clause ("par la loi
    n° 1.549 ... et l'Ordonnance Souveraine n° 10.124 ..."). Acts cited inside its notes, and articles of other acts
    ("à compter de la date prévue à l'article 127 de la loi ..."), are not causes and are left out."""
    out: list[dict] = []
    if aside is None:
        return out
    for p in aside:
        if not isinstance(p.tag, str) or p.tag != 'p':
            continue
        seq: list = []

        def walk(x):
            if not isinstance(x.tag, str):
                return
            if classes(x) & {'note'} or x.tag == 'sup':
                seq.append(x.tail or '')
                return
            if x.tag == 'u' and x.get('data-nature') and x.get('data-number') and not x.get('data-articles'):
                seq.append({'nature': x.get('data-nature'), 'number': x.get('data-number'), 'date': x.get('data-date')})
                seq.append(x.tail or '')
                return
            seq.append(x.text or '')
            for c in x:
                walk(c)
            if x is not p:
                seq.append(x.tail or '')
        walk(p)
        text, group = '', None
        for item in seq:
            if isinstance(item, str):
                text += item
                continue
            between = clean(text)
            if group is not None and re.fullmatch(r"(?:et|,)\s*(?:l[’']\s*|la |le )?", between):
                pass   # named jointly with the act before it, in the same clause
            else:
                group = len(out)
                clause = text.split(';')[-1]
                m = re.search(r'à compter du ([^;]*?)(?: par|$)', clean(clause))
                day = parse_fr_date(m.group(1)) if m else None
                cur_day = day
            out.append({'law': law_key(item), 'day': cur_day, 'group': group})
            text = ''
    return out


def histo_laws(aside) -> list[dict]:
    """The acts named by a "Historique de consolidation", in order, without those cited inside its notes."""
    seen = []
    for c in histo_clauses(aside):
        n, num, d = c['law'].split('/')
        law = {'nature': n, 'number': num, 'date': d}
        if law not in seen:
            seen.append(law)
    return seen


def histo_text(aside) -> str:
    if aside is None:
        return ''
    return clean(' '.join(words_of(p) for p in aside if isinstance(p.tag, str) and p.tag == 'p'))


def law_key(l: dict) -> str:
    return f'{l["nature"]}/{l["number"]}/{l["date"]}'


def article_slug(number: str) -> str:
    """'1er' -> '1er', '3-1' -> '3-1', 'préliminaire' -> 'preliminaire': the file name of the article."""
    s = unicodedata.normalize('NFKD', number.lower())
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s


def own(e, cls: str):
    """The first direct child of e's section_co with the class."""
    for c in e:
        if isinstance(c.tag, str) and cls in classes(c):
            return c
    return None


def read_version(raw: bytes) -> dict:
    """One consolidated version: its title, preamble and articles (those with text), each with its history."""
    doc = lhtml.fromstring(raw)
    content = doc.get_element_by_id('content')
    h1 = content.find('.//h1')
    units: dict[str, dict] = {}
    order: list[str] = []
    title = clean(words_of(h1)) if h1 is not None else ''
    doc_histo = own(content, 'histo')
    units['intitule'] = {'key': 'intitule', 'label': 'Intitulé', 'section': [], 'lines': [{'level': 0, 'text': title}],
                         'laws': histo_laws(doc_histo), 'clauses': histo_clauses(doc_histo), 'histo': histo_text(doc_histo)}
    order.append('intitule')
    pre = [c for c in content if isinstance(c.tag, str) and c.tag == 'section' and classes(c) == {'block'}]
    pre_lines = [l for s in pre for l in lines_of(s)]
    if pre_lines:
        units['preambule'] = {'key': 'preambule', 'label': 'Préambule', 'section': [], 'lines': pre_lines, 'laws': [],
                              'clauses': [], 'histo': ''}
        order.append('preambule')
    all_laws = {law_key(l): l for a in content.iter('aside') if 'histo' in classes(a) for l in histo_laws(a)}
    for sec in content.iter('section'):
        if 'art' not in classes(sec):
            continue
        num = sec.find('.//span[@class="number "]')
        number = clean(words_of(num)) if num is not None else clean((sec.get('data-title') or '').replace('Article', ''))
        key = article_slug(number)
        co = own(sec, 'section_co')
        # Usually one text block; some versions print part of the history as a text block of its own before it.
        texts = [c for c in co if isinstance(c.tag, str) and 'text' in classes(c)] if co is not None else []
        histo = own(co, 'histo') if co is not None else None
        path = []
        for anc in sec.iterancestors('section'):
            if 'legContainer' in classes(anc):
                tt = anc.find('./h2//span[@class="title_text"]')
                if tt is None:
                    tt = anc.find('.//span[@class="title_text"]')
                if tt is not None:
                    path.append(clean(words_of(tt)))
        if key in units:
            raise SystemExit(f'two articles numbered {number}')
        units[key] = {'key': key, 'label': f'Article {number}', 'section': list(reversed(path)),
                      'lines': [l for t in texts for l in lines_of(t)], 'laws': histo_laws(histo),
                      'clauses': histo_clauses(histo), 'histo': histo_text(histo)}
        order.append(key)
    return {'title': title, 'units': units, 'order': order, 'doc_laws': histo_laws(doc_histo),
            'doc_histo': histo_text(doc_histo), 'all_laws': all_laws}


def page_info(raw: bytes) -> dict:
    """The title and the 'Publication' line (Journal de Monaco) of a text's page."""
    doc = lhtml.fromstring(raw)
    content = doc.get_element_by_id('content')
    h1 = content.find('.//h1')
    info = {}
    for b in content.iter('div'):
        if 'infoBlock' not in classes(b):
            continue
        lab, val = b.find('i'), b.find('div')
        if lab is not None and val is not None:
            info[clean(words_of(lab))] = clean(val.text_content())
    pub = info.get('Publication', '')
    day = parse_fr_date(pub)
    return {'title': clean(words_of(h1)) if h1 is not None else '',
            'publication': f'{day} ({pub})' if day else pub}


# ---------------------------------------------------------------- dates and names

MONTHS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre',
          'décembre']


def fr_date(day: str) -> str:
    d = dt.date.fromisoformat(day)
    return f'{"1er" if d.day == 1 else d.day} {MONTHS[d.month - 1]} {d.year}'


def parse_fr_date(s: str) -> str | None:
    m = re.search(r'(\d{1,2})(?:er)? (' + '|'.join(MONTHS) + r') (\d{4})', s)
    if not m:
        return None
    return f'{int(m.group(3)):04d}-{MONTHS.index(m.group(2)) + 1:02d}-{int(m.group(1)):02d}'


KINDS = {'loi': 'Loi', 'ordonnance': 'Ordonnance Souveraine', 'arrete-ministeriel': 'Arrêté ministériel',
         'decision': 'Décision'}


def law_name(key: str) -> str:
    nature, number, date = key.split('/')
    return f'{KINDS.get(nature, nature.capitalize())} n° {number} du {fr_date(date)}'


def law_email(key: str) -> str:
    nature, number, _ = key.split('/')
    return f'{nature}-{number.replace(".", "")}@legimonaco.invalid'


def law_tag(key: str) -> str:
    nature, number, _ = key.split('/')
    return f'{nature}/{number.replace(".", "")}'


def law_url(key: str) -> str | None:
    nature, number, date = key.split('/')
    if nature != 'loi':
        return None
    return f'{BASE}/tnc/loi/{date[:4]}/{date[5:7]}-{date[8:]}-{number}/'


# ---------------------------------------------------------------- the record of one act

def text_of(u: dict | None):
    return None if not u or not u['lines'] else tuple((l['level'], l['text']) for l in u['lines'])


def spacing_only(a, b) -> bool:
    if a is None or b is None:
        return False
    squash = lambda t: re.sub(r'\s+', '', ''.join(x[1] for x in t))
    return squash(a) == squash(b)


def cause_of(k: str, i: int, day: str, parsed: list[dict], a, b, window: list[str]) -> dict:
    """Why article k changed in version i, from that version's own history of the article:
    1. the history names one act whose clause takes effect on this very day ("modifié à compter du <day> par ...");
    2. else the history names exactly one act it did not name in the version before ("history"), or several of which
       exactly one appears in the whole text for the first time in this version ("history+window");
    3. else, the words changed only by spacing ("typesetting"), or the version brings back the text of an earlier
       version ("reverted"), or nothing explains the change ("unexplained").
    Acts named jointly in one clause (a law "et" an ordonnance) are two possible causes: neither is credited."""
    prev, cur = parsed[i - 1]['units'].get(k), parsed[i]['units'].get(k)
    clauses = (cur or {}).get('clauses') or []
    before = {law_key(l) for l in ((prev or {}).get('laws') or [])}
    groups: dict[int, list] = {}
    for c in clauses:
        groups.setdefault(c['group'], []).append(c)
    dated = [g for g in groups.values() if g[0]['day'] == day]
    fresh = [g for g in groups.values() if any(c['law'] not in before for c in g)]
    named = sorted({c['law'] for c in clauses})

    def credit(g: list, evidence: str) -> dict:
        if len({c['law'] for c in g}) > 1:
            return {'kind': 'unexplained', 'cause': None, 'evidence': 'joint', 'candidates': sorted({c['law'] for c in g})}
        out = {'kind': 'law', 'cause': g[0]['law'], 'evidence': evidence}
        if g[0]['day'] and g[0]['day'] != day:
            out['law_day'] = g[0]['day']
        return out
    if len(dated) == 1:
        return credit(dated[0], 'history-date')
    if len(dated) > 1:
        return {'kind': 'unexplained', 'cause': None, 'evidence': 'several', 'candidates': sorted({c['law'] for g in dated for c in g})}
    if len(fresh) == 1:
        return credit(fresh[0], 'history')
    if len(fresh) > 1:
        inw = [g for g in fresh if any(c['law'] in window for c in g)]
        if len(inw) == 1:
            return credit(inw[0], 'history+window')
        return {'kind': 'unexplained', 'cause': None, 'evidence': 'several', 'candidates': sorted({c['law'] for g in fresh for c in g})}
    if spacing_only(a, b):
        return {'kind': 'typesetting', 'cause': None, 'evidence': 'spacing'}
    earlier = [j for j in range(i - 1) if text_of(parsed[j]['units'].get(k)) == b]
    if earlier:
        return {'kind': 'reverted', 'cause': None, 'evidence': 'reverted', 'same_as': earlier[-1], 'candidates': named}
    return {'kind': 'unexplained', 'cause': None, 'evidence': 'none', 'candidates': named}


def build_act(act: dict, offline: bool) -> dict:
    days = version_days(act, offline)
    srcs, parsed = [], []
    for d in days:
        url = version_url(act, d)
        raw = fetch(url, offline)
        srcs.append({'from': d, 'url': url, 'sha256': hashlib.sha256(raw).hexdigest()})
        parsed.append(read_version(raw))
    changes: list[dict] = []
    for i in range(1, len(srcs)):
        prev, cur = parsed[i - 1], parsed[i]
        day = srcs[i]['from']
        # The acts the whole text names for the first time in this version: those that took effect since the last.
        window = sorted(set(cur['all_laws']) - set(prev['all_laws']))
        for k in sorted(set(prev['units']) | set(cur['units'])):
            pu, cu = prev['units'].get(k), cur['units'].get(k)
            a, b = text_of(pu), text_of(cu)
            if a == b:
                continue
            rec = {'key': k, 'day': day, 'version': i, 'unit': cu if b else pu, 'created': a is None,
                   'repealed': b is None, 'window': window}
            rec.update(cause_of(k, i, day, parsed, a, b, window))
            changes.append(rec)
    return {'act': act, 'sources': srcs, 'parsed': parsed, 'changes': changes}


# ---------------------------------------------------------------- the git repository

def git(repo: Path, *args: str, env: dict | None = None, input: str | None = None) -> str:
    out = subprocess.run(['git', *args], cwd=repo, capture_output=True, text=True, encoding='utf-8', env=env, input=input)
    if out.returncode:
        raise SystemExit(f'git {" ".join(args)} failed: {out.stderr}')
    return out.stdout


def last_sunday(year: int, month: int) -> dt.date:
    d = (dt.date(year, month + 1, 1) if month < 12 else dt.date(year + 1, 1, 1)) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def monaco_offset(day: dt.date) -> int:
    """Hours ahead of UTC in Monaco on a day (Central European Time, as in France): summer time from 1976, ending on
    the last Sunday of September until 1995 and of October since 1996, starting on the last Sunday of March (1976:
    28 March; 1977-1980 the first Sunday of April). Only days from 1970 are asked for."""
    if day.year < 1976:
        return 1
    if day.year == 1976:
        start, end = dt.date(1976, 3, 28), dt.date(1976, 9, 26)
    else:
        if day.year <= 1980:
            start = dt.date(day.year, 4, 1) + dt.timedelta(days=(6 - dt.date(day.year, 4, 1).weekday()) % 7)
        else:
            start = last_sunday(day.year, 3)
        end = last_sunday(day.year, 9 if day.year <= 1995 else 10)
    return 2 if start <= day < end else 1


def commit_date(day: str, clamp: int) -> str:
    """Noon in Monaco on the day. Git cannot store a date before 1970: those commits are dated 1970-01-01, one second
    apart in order, and the real day is in the In-force trailer and the tags."""
    if day < '1970-01-01':
        return f'@{clamp} +0000'
    d = dt.date.fromisoformat(day)
    off = monaco_offset(d)
    stamp = int(dt.datetime(d.year, d.month, d.day, 12, tzinfo=dt.timezone(dt.timedelta(hours=off))).timestamp())
    return f'@{stamp} +0{off}00'


def render(u: dict) -> str:
    """One article as a Markdown file: its number as the title, then one line per alinéa or list item. The act's title
    and preamble files hold their words only."""
    out = [] if u['key'] in ('intitule', 'preambule') else ['# ' + u['label'], '']
    for l in u['lines']:
        out += [('  ' * (l['level'] - 1) + '- ' + l['text']) if l['level'] else l['text'], '']
    return '\n'.join(out).rstrip() + '\n'


SUFFIXES = ['', 'bis', 'ter', 'quater', 'quinquies', 'sexies', 'septies', 'octies', 'nonies', 'decies']


def unit_order(key: str) -> tuple:
    if key == 'intitule':
        return (0, 0, ())
    if key == 'preambule':
        return (1, 0, ())
    if key == 'preliminaire':
        return (2, 0, ())
    m = re.fullmatch(r'(\d+)(er)?(.*)', key)
    if not m:
        return (4, 0, (key,))
    rest = tuple(int(x) if x.isdigit() else (SUFFIXES.index(x) if x in SUFFIXES else 99) for x in m.group(3).split('-') if x)
    return (3, int(m.group(1)), rest)


def file_name(key: str) -> str:
    return f'{key}.md' if key in ('intitule', 'preambule') else f'article-{key}.md'


def short_label(u: dict) -> str:
    return u['label'].replace('Article ', 'Art. ')


def write_repo(repo: Path, built: list[dict], laws: dict[str, dict], docs: Path, today: str):
    remote = None
    if (repo / '.git').exists():
        out = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=repo, capture_output=True, text=True)
        remote = out.stdout.strip() or None

    def force(fn, path, _exc):
        os.chmod(path, 0o700)
        fn(path)
    if repo.exists():
        for p in repo.iterdir():
            shutil.rmtree(p, onexc=force) if p.is_dir() else p.unlink()
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, 'init', '-q', '-b', 'main')
    git(repo, 'config', 'core.autocrlf', 'false')
    git(repo, 'config', 'core.quotepath', 'false')
    if remote:
        git(repo, 'remote', 'add', 'origin', remote)

    rank = {'original': 0, 'law': 1, 'typesetting': 2, 'reverted': 3, 'unexplained': 4}
    events: dict[tuple, list] = {}
    for b in built:
        p0 = b['parsed'][0]
        events[(b['sources'][0]['from'], b['act']['slug'], 'original', '')] = [
            {'key': k, 'unit': u, 'kind': 'original', 'repealed': False, 'created': True, 'evidence': 'original'}
            for k, u in p0['units'].items() if u['lines']]
        for c in b['changes']:
            group = c['cause'] or (c['evidence'] if c['kind'] == 'unexplained' else '')
            events.setdefault((c['day'], b['act']['slug'], c['kind'], group), []).append(c)
    by_slug = {b['act']['slug']: b for b in built}
    order = sorted(events, key=lambda e: (e[0], e[1], rank[e[2]], e[3]))
    tags: dict[str, str] = {}
    commits: list[dict] = []
    clamp = 0
    future = False
    for ev in order:
        day, slug, kind, cause = ev
        cause = cause if kind == 'law' else None
        b = by_slug[slug]
        act, short = b['act'], b['act']['short']
        if day > today and not future:
            git(repo, 'checkout', '-q', '-b', 'futur')
            future = True
        items = sorted(events[ev], key=lambda c: unit_order(c['key']))
        for c in items:
            path = repo / slug / file_name(c['key'])
            path.parent.mkdir(parents=True, exist_ok=True)
            if c['repealed']:
                path.unlink(missing_ok=True)
            else:
                path.write_text(render(c['unit']), encoding='utf-8', newline='\n')
        git(repo, 'add', '-A')
        if day < '1970-01-01':
            clamp += 1
        src = next(s for s in b['sources'] if s['from'] == day)
        labels = ', '.join(short_label(c['unit']) for c in items)
        affecting = ', '.join(f'{slug}/{file_name(c["key"])}' for c in items)
        if len(items) > 20:
            affecting = (f'{slug}/ ({sum(1 for c in items if not c["repealed"])} files written, '
                         f'{sum(1 for c in items if c["repealed"])} removed; listed in the diff)')
            labels = f'{len(items)} articles'
        groups = {'Inséré': [c for c in items if c['created']], 'Abrogé': [c for c in items if c['repealed']],
                  'Modifié': [c for c in items if not c['created'] and not c['repealed']]}
        lists = [f'{name} : {", ".join(short_label(c["unit"]) for c in cs)}' for name, cs in groups.items() if cs]
        trailers = []
        if kind == 'original':
            author, email = act['author']
            info = b['info']
            msg = [f'{short} : texte d’origine ({author})', '', b['parsed'][0]['title'], '',
                   f'Le texte de la première version consolidée de Legimonaco, en vigueur le {fr_date(day)} : '
                   f'{sum(1 for c in items if c["key"] not in ("intitule", "preambule"))} articles.',
                   'The text of Legimonaco’s first consolidated version, in force on this day.', '']
            trailers.append(f'Enacted: {act["enacted"]}')
            if info.get('publication'):
                trailers.append(f'Published: {info["publication"]}')
        elif kind == 'law':
            rec = laws.get(cause, {})
            author, email = law_name(cause), law_email(cause)
            msg = [f'{short} : {labels} ({author})', '', rec.get('title') or author, ''] + lists + ['']
            ev_kinds = sorted({c['evidence'] for c in items})
            if 'history-date' in ev_kinds:
                msg += ['Pour ' + ', '.join(short_label(c['unit']) for c in items if c['evidence'] == 'history-date')
                        + f' : l’historique de l’article nommait déjà cette loi ; il précise qu’elle le modifie à compter du {fr_date(day)}.',
                        'Credited by the article’s history, which names this law with effect from this day.', '']
            early = sorted({c['law_day'] for c in items if c.get('law_day')})
            if early:
                msg += ['L’historique de l’article donne à ces modifications un autre jour d’effet ('
                        + ', '.join(fr_date(x) for x in early) + ') que la version de Legimonaco qui les imprime',
                        f'({fr_date(day)}). Le registre suit la version ; le jour de l’historique est dans Law-in-force.',
                        'The article’s history gives these changes another day of effect than the Legimonaco version that',
                        'prints them; the record follows the version and keeps the history’s day in Law-in-force.', '']
            trailers.append('Evidence: ' + '; '.join(f'{c["key"]} {c["evidence"]}' for c in items))
            trailers.append(f'Enacted: {cause.split("/")[2]}')
            if rec.get('publication'):
                trailers.append(f'Published: {rec["publication"]}')
            for x in early:
                trailers.append(f'Law-in-force: {x} (the article’s history; the Legimonaco version prints the change from {day})')
        elif kind == 'typesetting':
            author, email = PUBLISHER
            msg = [f'{short} : {labels}, mise en forme (aucune loi)', '',
                   'Le texte consolidé de Legimonaco ne change ici que par des espaces. Aucune loi n’en est la cause ;',
                   'le texte est repris tel que publié.', '',
                   'Only the spacing of Legimonaco’s consolidated text changed. No law is credited.', '']
            trailers.append('Kind: typesetting')
        elif kind == 'reverted':
            author, email = PUBLISHER
            back = sorted({b['sources'][c['same_as']]['from'] for c in items})
            msg = [f'{short} : {labels}, texte antérieur rétabli par Legimonaco (aucune loi)', '',
                   'La version consolidée de ce jour imprime de nouveau le texte d’une version antérieure ('
                   + ', '.join(fr_date(x) for x in back) + ').',
                   'Aucune loi nouvelle n’est nommée par l’historique de ces articles. Le texte est repris tel que publié,',
                   'sans être attribué à une loi.', '',
                   'Legimonaco’s consolidated version of this day prints again the text of an earlier version. No new law',
                   'is named in these articles’ history. The text is kept as published and credited to no law.', '']
            trailers.append('Kind: reverted')
            trailers += [f'Same-text-as: {x}' for x in back]
        else:
            author, email = PUBLISHER
            cands = sorted({x for c in items for x in c.get('candidates', [])})
            joint = any(c.get('evidence') == 'joint' for c in items)
            msg = [f'{short} : {labels}, modification non expliquée (aucune loi)', '',
                   'Le texte consolidé de Legimonaco change ces articles ce jour-là, mais l’historique de consolidation',
                   'de la version ne permet pas de les rattacher à une seule loi'
                   + (' : il nomme ensemble une loi et une ordonnance souveraine.' if joint else '.'),
                   'Le texte est repris tel que publié, sans être attribué à une loi.', '',
                   'Legimonaco’s consolidated text changed these articles on this day, but the version’s own history',
                   'does not link the change to one law. The text is kept as published and credited to no law.', '']
            trailers.append('Kind: unexplained')
            trailers += [f'Named-in-history: {law_name(x)}' for x in cands]
        if day < '1970-01-01':
            trailers.append('Date-note: git cannot store dates before 1970; the commit is dated 1970-01-01 and In-force is the real day')
        trailers += [f'In-force: {day}', f'Affecting: {affecting}']
        if kind == 'law' and law_url(cause):
            trailers.append(f'Source: {law_url(cause)}')
        trailers.append(f'Text: {src["url"]}')
        when = commit_date(day, clamp)
        env = {**os.environ, 'GIT_AUTHOR_NAME': author, 'GIT_AUTHOR_EMAIL': email, 'GIT_AUTHOR_DATE': when,
               'GIT_COMMITTER_NAME': COMMITTER[0], 'GIT_COMMITTER_EMAIL': COMMITTER[1], 'GIT_COMMITTER_DATE': when}
        git(repo, 'commit', '-q', '--allow-empty', '-F', '-', env=env, input='\n'.join(msg + trailers) + '\n')
        head = git(repo, 'rev-parse', 'HEAD').strip()
        tags[f'{slug}/{day}'] = head
        if kind == 'law':
            tags[law_tag(cause)] = head
        commits.append({'day': day, 'act': slug, 'kind': kind, 'cause': cause, 'articles': [c['key'] for c in items],
                        'evidence': [c.get('evidence') for c in items], 'hash': head})
    for name, head in tags.items():
        git(repo, 'tag', '-f', name, head)
    if future:
        git(repo, 'checkout', '-q', 'main')
    history_tip = git(repo, 'rev-parse', 'HEAD').strip()
    # Documentation, tables, the tools and the record of how the repository was made come last, by Lexifina, dated
    # the data's retrieval day, so the same data gives the same hashes.
    for p in sorted(docs.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            dest = repo / p.relative_to(docs)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(p.read_bytes())
    for name in ('build.py', 'reproduce.py', 'check_repo.py', 'test_repo.py'):
        (repo / 'tools' / name).write_bytes((HERE / name).read_bytes())
    write_tables(repo, built, laws, commits, today)
    write_manifest(repo, built, today)
    write_reproduce(repo, built, commits, tags, REQUESTS, today, history_tip)
    git(repo, 'add', '-A')
    when = commit_date(today, 0)
    env = {**os.environ, 'GIT_AUTHOR_NAME': COMMITTER[0], 'GIT_AUTHOR_EMAIL': COMMITTER[1], 'GIT_AUTHOR_DATE': when,
           'GIT_COMMITTER_NAME': COMMITTER[0], 'GIT_COMMITTER_EMAIL': COMMITTER[1], 'GIT_COMMITTER_DATE': when}
    git(repo, 'commit', '-q', '-m', 'Documentation, tableaux, outils et REPRODUCE.md', env=env)
    if future:
        git(repo, 'checkout', '-q', 'futur')
        git(repo, 'merge', '-q', '--no-edit', 'main', env=env)
        git(repo, 'checkout', '-q', 'main')
    return commits, tags, history_tip


def csv_text(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator='\n')
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def write_tables(repo: Path, built: list[dict], laws: dict[str, dict], commits: list[dict], today: str):
    rows = []
    for key in sorted(laws, key=lambda x: (x.split('/')[2], x)):
        rec = laws[key]
        mine = [c for c in commits if c['cause'] == key]
        rows.append({'texte': law_name(key), 'titre': rec.get('title', ''), 'publication': rec.get('publication', ''),
                     'auteur': f'{law_name(key)} <{law_email(key)}>', 'tag': law_tag(key),
                     'en_vigueur_dans_le_registre': ' '.join(sorted({c['day'] for c in mine})),
                     'articles': ' '.join(f'{c["act"]}:{k}' for c in mine for k in c['articles']),
                     'source': law_url(key) or ''})
    (repo / 'lois.csv').write_text(csv_text(rows), encoding='utf-8', newline='\n')
    for b in built:
        act = b['act']
        units: dict[str, dict] = {}
        for p in b['parsed']:
            for k, u in p['units'].items():
                if u['lines']:
                    units[k] = u
        last = b['parsed'][-1]['units']
        out = [f'# {b["parsed"][-1]["title"]}', '',
               f'Legimonaco <{BASE}{act["path"]}> · {len(b["sources"])} versions, {b["sources"][0]["from"]} to {b["sources"][-1]["from"]}', '',
               '| Article | Division | Changes in the record | Last changed | Now |', '| --- | --- | ---: | --- | --- |']
        for k in sorted(units, key=unit_order):
            cs = [c for c in b['changes'] if c['key'] == k and c['day'] <= today]
            live = bool(last.get(k) and last[k]['lines'])
            u = last[k] if live else units[k]
            name = u['label']
            out.append(f'| {f"[{name}]({file_name(k)})" if live else name} | {" › ".join(u["section"])} | {len(cs)} | '
                       f'{cs[-1]["day"] if cs else ""} | {"in force" if live else "repealed"} |')
        (repo / act['slug'] / 'README.md').write_text('\n'.join(out) + '\n', encoding='utf-8', newline='\n')


# ---------------------------------------------------------------- main

def build_all(offline: bool) -> tuple[list[dict], dict[str, dict]]:
    built = [build_act(a, offline) for a in ACTS]
    for b in built:
        b['info'] = page_info(fetch(version_url(b['act'], b['sources'][0]['from']), offline))
    keys = sorted({c['cause'] for b in built for c in b['changes'] if c['cause']})
    laws = {}
    for k in keys:
        url = law_url(k)
        laws[k] = page_info(fetch(url, offline)) if url else {}
    return built, laws


def data_day() -> str:
    """The day the cached source data was retrieved (the newest file in the cache), so the documentation commit made by
    a rebuild on any later day carries the same date."""
    files = [p for p in CACHE.iterdir() if p.name != '.gitignore'] if CACHE.exists() else []
    if not files:
        return dt.date.today().isoformat()
    return dt.date.fromtimestamp(max(p.stat().st_mtime for p in files)).isoformat()


def verify_rebuild(repo: str, today: str | None):
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        out = subprocess.run([os.sys.executable, '-X', 'utf8', str(HERE / 'build.py'), '--offline', '--repo', tmp]
                             + (['--today', today] if today else []), capture_output=True, text=True)
        if out.returncode:
            raise SystemExit(out.stderr)

        def hashes(r):
            log = git(Path(r), 'log', '--format=%H', 'main').split()
            tags = dict(l.split(' ', 1)[::-1] for l in git(Path(r), 'show-ref', '--tags').split('\n') if l)
            return log, tags
        a, b = hashes(repo), hashes(tmp)
        same_history = a[0][1:] == b[0][1:]
        rec = {'identical': same_history and a[1] == b[1], 'history_tip': a[0][1], 'commits': len(a[0]) - 1,
               'tags': len(a[1]), 'main_identical': a[0][0] == b[0][0], 'main': a[0][0], 'rebuilt_main': b[0][0]}
        print(json.dumps(rec, indent=1))
        p = HERE / 'verification.json'
        ver = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
        ver['rebuild'] = {k: rec[k] for k in ('identical', 'history_tip', 'commits', 'tags')}
        p.write_text(json.dumps(ver, indent=1, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
        # Git marks its objects read-only; clear the flag so the temporary folder can be removed on Windows.
        for f in Path(tmp).rglob('*'):
            os.chmod(f, 0o700)
        raise SystemExit(0 if rec['identical'] else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', default=str(ROOT.parent / 'monaco-law'))
    ap.add_argument('--offline', action='store_true', help='read only the cache; fail on anything not cached')
    ap.add_argument('--today', default=None, help='the data\'s retrieval day (default: the newest file in the cache)')
    ap.add_argument('--verify-rebuild', action='store_true',
                    help='build again into a temporary folder from the cache, compare every hash with --repo, and record the result')
    args = ap.parse_args()
    if args.verify_rebuild:
        verify_rebuild(args.repo, args.today)
    built, laws = build_all(args.offline)
    today = args.today or data_day()
    for b in built:
        kinds: dict[str, int] = {}
        for c in b['changes']:
            k = c['kind'] + ('/' + c['evidence'] if c['kind'] == 'law' else '')
            kinds[k] = kinds.get(k, 0) + 1
        print(f'{b["act"]["slug"]}: {len(b["sources"])} versions {b["sources"][0]["from"]}..{b["sources"][-1]["from"]}, '
              f'{len(b["changes"])} article changes {dict(sorted(kinds.items()))}')
        for c in b['changes']:
            if c['kind'] == 'unexplained':
                print(f'   unexplained {c["day"]} {c["key"]}: candidates {c.get("candidates")} window {c["window"]}')
    commits, tags, tip = write_repo(Path(args.repo), built, laws, HERE / 'repo', today)
    print(f'repo: {len(commits)} history commits + 1 documentation commit, {len(tags)} tags, history tip {tip} -> {args.repo}')


if __name__ == '__main__':
    main()
