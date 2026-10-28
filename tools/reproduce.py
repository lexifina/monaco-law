"""Writes data/versions.json and REPRODUCE.md into the Monaco law repository, from the facts of the build that made it.
Called by build.py; kept apart so the record of how the repository was made reads as one document.

The results of the checks (check_repo.py), of the hash-for-hash rebuild (build.py --verify-rebuild) and of the smoke
test (test_repo.py) are read from verification.json beside this file; a build made before them says they have not
been run."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = 'https://legimonaco.mc'


def write_manifest(repo: Path, built: list[dict], today: str):
    """Every source page the text comes from, with its sha256, so a rebuild or a check can show it read the same bytes."""
    out = {'built': today, 'acts': [{
        'slug': b['act']['slug'], 'legimonaco': BASE + b['act']['path'],
        'versions': [{'from': s['from'], 'url': s['url'], 'sha256': s['sha256']} for s in b['sources']],
    } for b in built]}
    (repo / 'data').mkdir(exist_ok=True)
    (repo / 'data' / 'versions.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    # The corpus description shared by every git-for-law repository (shape set by lexifina/global-law).
    corpus = {
        'corpus': 'mc/national/acts',
        'name': 'Monaco: Constitution and loi n° 1.362',
        'history_from': min(b['sources'][0]['from'] for b in built),
        'built': today,
        'dates': {'commit': 'in-force', 'other_trailers': ['Enacted', 'Published', 'Law-in-force'],
                  'time': '12:00 Europe/Monaco (CET/CEST); before 1970 clamped to 1970-01-01, real day in In-force'},
        'scope': {
            'trailer': 'Applies',
            'when_absent': 'no scope note is recorded in this corpus; not a statement that the change reaches every case',
            'default_reach': {
                'rule': 'non-retroactivity of statutes',
                'meaning': 'a law provides only for the future and has no retroactive effect, unless it says otherwise',
                'authority': "Code civil de Monaco, article 2: « La loi ne dispose que pour l'avenir ; elle n'a point d'effet rétroactif. »",
                'decided_here': False,
            },
        },
        'tool': 'tools/en_vigueur_au.py',
    }
    (repo / 'corpus.json').write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def _verification() -> dict:
    p = HERE / 'verification.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def write_reproduce(repo: Path, built: list[dict], commits: list[dict], tags: dict, requests: list[dict], today: str,
                    history_tip: str):
    blob = subprocess.run(['git', 'hash-object', str(HERE / 'build.py')], capture_output=True, text=True).stdout.strip()
    pyv = subprocess.run(['python', '--version'], capture_output=True, text=True).stdout.strip()
    gitv = subprocess.run(['git', '--version'], capture_output=True, text=True).stdout.strip()
    import lxml
    files = {r['file'] for r in requests if r['file'].exists()}
    days = sorted({dt.date.fromtimestamp(f.stat().st_mtime).isoformat() for f in files})
    urls = sorted({r['url'] for r in requests})
    changes = [c for b in built for c in b['changes']]
    count = lambda pred: sum(1 for c in changes if pred(c))
    kinds = {k: sum(1 for c in commits if c['kind'] == k) for k in ('original', 'law', 'typesetting', 'reverted', 'unexplained')}
    clamped = sum(1 for c in commits if c['day'] < '1970-01-01')
    rows = '\n'.join(
        f'| {b["act"]["short"]} | `{BASE}{b["act"]["path"]}` | {len(b["sources"])} | {b["sources"][0]["from"]} to '
        f'{b["sources"][-1]["from"]} | {len(b["changes"])} |' for b in built)

    def listing(kind: str) -> str:
        return '\n'.join(f'- {c["act"]} {c["day"]}: {", ".join(c["articles"])}' for c in commits if c['kind'] == kind) or '- none'
    early = '\n'.join(f'- {c["act"]} {c["day"]} {c["key"]}: {c["cause"]}, history says {c["law_day"]}'
                      for b in built for c in [dict(x, act=b['act']['slug']) for x in b['changes']] if c.get('law_day')) or '- none'
    v = _verification()
    check = v.get('check')
    check_text = (f'`{check["versions"]} versions checked ({check["files"]} files compared byte for byte), '
                  f'{check["mismatches"]} mismatches; {check["wordcheck"]} versions checked word for word against the '
                  f'whole page, {check["word_mismatches"]} mismatches` (against history tip `{check["history_tip"]}`).'
                  if check else '*Not yet run for this build.*')
    det = v.get('rebuild')
    det_text = (f'`python -X utf8 scripts/monaco-law/build.py --offline --verify-rebuild` built the repository again from '
                f'the cache into an empty temporary folder and compared every commit and tag: identical = '
                f'`{str(det["identical"]).lower()}` for {det["commits"]} history commits and {det["tags"]} tags (history tip '
                f'`{det["history_tip"]}`). This documentation commit then records that result, so the same command run '
                'on this build compares `main` itself too.' if det else '*Not yet run for this build.*')
    smoke = v.get('smoke')
    smoke_text = ('\n'.join(f'   - {"PASS" if ok else "FAIL"}: {name}' for name, ok in smoke['results'])
                  + f'\n\n   {sum(1 for _, ok in smoke["results"] if ok)} of {len(smoke["results"])} passed (against history tip `{smoke["head"]}`).'
                  if smoke else '   *Not yet run for this build.*')

    text = f"""# How this history was made, and how to make it again

This file records exactly how the repository was built: the sources, the commands, the software, the decisions made
by hand, and what an AI model did and did not do. The build writes it, so it describes the build that made this
commit.

## Short version

```sh
git clone https://github.com/lexifina/monaco-law && cd monaco-law
pip install lxml
python -X utf8 tools/build.py --repo ../rebuilt --today {today}
git -C ../rebuilt rev-parse main        # the same hash as this repository's main
python -X utf8 tools/check_repo.py --repo ../rebuilt --no-record
python -X utf8 tools/test_repo.py --repo ../rebuilt --no-record
```

`tools/build.py` needs Python 3.12 or later with `lxml`, and git. It reads Legimonaco (or its own cache, `.cache/`
beside it) and writes this repository into `--repo`. With the same Legimonaco pages and the same `--today` it gives the
same commits with the same hashes. `data/versions.json` lists every source page with its sha256. `--offline` refuses
to touch the network and fails on anything not cached. Legimonaco pages carry no stable version stamp, so a fresh
download on a later day may differ; the sha256 values say whether it does.

## Sources

All legal text and all information about changes come from **Legimonaco** (https://legimonaco.mc), the official legal
database of the Principality of Monaco (Gouvernement Princier). Nothing was typed in, summarised or rewritten. The
build read {len(urls)} pages.

| What | Where |
| --- | --- |
| Each text's consolidated versions and the day each applies from | `<text>?versions` (JSON: `previousVersions`, `currentVersion`, `nextVersions`) |
| The text of each version | `<text>@YYYY.MM.DD/` (HTML), listed with sha256 in `data/versions.json` |
| Which act created, amended or repealed each article, and from which day | each article's "Historique de consolidation" in that version (`aside.histo`: `<u data-nature data-number data-date>` and the words "à compter du …") |
| Each amending law's title and publication in the Journal de Monaco | the law's own page, `/tnc/loi/YYYY/MM-DD-N.NNN/` ("Publication") |

| Act | Legimonaco | Versions | From | Article changes |
| --- | --- | ---: | --- | ---: |
{rows}

The data was retrieved on {", ".join(days) if days else today}, one request at a time at least one second apart, with
the user agent `lexifina-watch/1.0 (+https://lexifina.com; corpus@lexifina.com)`.

## The build, step by step

1. `python -X utf8 scripts/monaco-law/build.py` in Lexifina's own repository fetched the pages and wrote this
   repository; every later build ran with `--offline`. `tools/build.py` here is the same file as
   `scripts/monaco-law/build.py` there (git blob `{blob}`), with `tools/reproduce.py`, which writes this file,
   `tools/check_repo.py` and `tools/test_repo.py`. The documentation commit is dated {today}, the day the data was
   retrieved (the newest file in the cache), not the day of the run.
2. `python -X utf8 scripts/monaco-law/check_repo.py` read every version back from git with
   `tools/en_vigueur_au.py`'s own lookup, on the day it applies from, and compared it with the official page:
   {check_text}
   File by file, the act's files on that day must be exactly the files the build's parser makes from that version's
   page. Word for word, the whole act printed by `tools/en_vigueur_au.py`, without its markdown marks, must have the
   same words in the same order as the page read independently of the parser (the text of every article section with
   its "Article N" heading, the title and the preamble, without the histories, notes and buttons).
3. {det_text}
4. `python -X utf8 scripts/monaco-law/test_repo.py` ran the functional smoke test against the built repository
   (standard library only):

{smoke_text}

5. `git push -f origin main --tags` published it to GitHub as a private repository.

It ran with {pyv}, lxml {lxml.__version__} and {gitv} on Windows 11. No network service other than Legimonaco is involved.

## How the text and the commits are derived

Everything below is done by `tools/build.py`, deterministically.

- **Texts.** For each act, every consolidated version Legimonaco lists. The Constitution has two (1962 and the 2002
  revision); loi n° 1.362 has {len(built[1]['sources'])}, from the text as first in force in 2009.
- **Text of an article.** Each article is one file, `<act>/article-<number>.md` (for example
  `loi-1362/article-22-2-1.md`, `constitution/article-1er.md`). Each paragraph and each list item is one line, list
  items as `- ` at their depth; numbering such as "1°)" is part of the printed words. The act's title is
  `intitule.md` (loi n° 1.362's title was replaced in 2023) and the Constitution's preamble `preambule.md`. Division
  headings (Titre, Chapitre, Section) are listed in each act's `README.md`, not in the history. Histories, editorial
  notes and links are left out. Spacing is collapsed. Nothing else is changed. An article with no text in a version
  (repealed, or kept only as a number) has no file.
- **Changes.** Consecutive versions are compared article by article. {len(changes)} article changes were found.
- **Cause.** Each changed article's history in the newer version is read as a list of clauses, each naming an act and,
  where it says so, the day it takes effect ("modifié à compter du 30 septembre 2023 par la loi n° 1.549 …"). The
  change is credited:
  - to the one act whose clause takes effect on the version's day (`Evidence: … history-date`,
    {count(lambda c: c['evidence'] == 'history-date')} article changes);
  - else to the one act the history names that the previous version's history did not (`history`,
    {count(lambda c: c['evidence'] == 'history')}), or, where it names several, the one of them that appears in the
    whole text for the first time in this version (`history+window`, {count(lambda c: c['evidence'] == 'history+window')}).
  Where nothing credits one act:
  - a change of spacing only is a **typesetting** commit by the publisher ({count(lambda c: c['kind'] == 'typesetting')} article changes);
  - a version that prints again the text of an earlier version, with no new act in the history, is a **reverted**
    commit by the publisher ({count(lambda c: c['kind'] == 'reverted')});
  - anything else is an **unexplained** commit by the publisher, credited to no act
    ({count(lambda c: c['kind'] == 'unexplained')}), including {count(lambda c: c['evidence'] == 'joint')} changes whose
    history names a law and an ordonnance souveraine jointly in one clause: two possible causes, so neither is credited.
- **Commits.** One commit per act per amending act per day ({kinds['law']} law commits), one for each act's first text
  ({kinds['original']}), {kinds['typesetting']} typesetting, {kinds['reverted']} reverted and {kinds['unexplained']}
  unexplained commits, in the order they took effect, then one for this documentation dated {today}.
  - The author is the act, named as Legimonaco names it (`Loi n° 1.462 du 28 juin 2018`), at an address that cannot
    exist (`loi-1462@legimonaco.invalid`), so `git blame` names the law. The first texts are by the act itself
    (`Constitution du 17 décembre 1962`, `Loi n° 1.362 du 3 août 2009`). Typesetting, reverted and unexplained commits
    are by `Legimonaco <legimonaco@legimonaco.invalid>`. Only the documentation commit is by Lexifina.
  - Author and committer dates are noon in Monaco (Central European Time, summer time by the European rules, coded in
    the script) on the day the version applies from. The committer is `Lexifina <monaco-law@lexifina.com>`.
  - Git cannot store dates before 1970. The {clamped} commit(s) before 1970 (the Constitution of 17 December 1962) are
    dated 1970-01-01, one second apart in order, and carry the real day in `In-force:`, in a `Date-note:` and in the
    tags. The reader `tools/en_vigueur_au.py` uses `In-force:`, not the commit date.
  - Trailers: `In-force:` (every commit), `Enacted:` (the act's date), `Published:` (the Journal de Monaco),
    `Law-in-force:` where the article's history gives the change another day than the version that prints it,
    `Evidence:`, `Affecting:`, `Source:` (the law) and `Text:` (the consolidated version), `Kind:` for the labelled
    commits, `Named-in-history:` and `Same-text-as:`.
  - Tags: each act's days (`loi-1362/2023-09-30`) and each amending act's last commit (`loi/1549`); {len(tags)} in all.

Changes printed by a version before the day their history gives (credited, with `Law-in-force:`):

{early}

Typesetting commits:

{listing('typesetting')}

Reverted commits:

{listing('reverted')}

Unexplained commits:

{listing('unexplained')}

## Decisions made by hand

These choices were made when the tool was written, after looking at the data. They are in the code.

1. **The acts.** The Constitution of 17 December 1962, with its one revision (loi n° 1.249 du 2 avril 2002), and loi
   n° 1.362 du 3 août 2009 on money laundering, terrorist financing and corruption: still in force, amended by {len({c['cause'] for c in commits if c['act'] == 'loi-1362' and c['kind'] == 'law'})}
   acts in {len(built[1]['sources']) - 1} later versions, and Legimonaco has its text as first in force. The
   data-protection law n° 1.165 of 1993, the other candidate, was set aside: its earliest version on Legimonaco is of
   2001 (the 1993 text is not served), and it was repealed in 2024. The Constitution of 5 January 1911 is on Legimonaco
   only as a PDF attached to the 1962 Constitution, with no consolidated versions; it is not in the record.
2. **Legimonaco's versions are followed as published**, including where a version prints a change before the day its
   history gives (2021-06-05) or prints an earlier text again (2021-08-31, 2021-12-31, 2023-08-12). Each such step is
   a commit, credited or labelled as above, so that every version reads back exactly.
3. **A law named jointly with an ordonnance souveraine** in one clause ("par la loi n° 1.549 … et l'Ordonnance
   Souveraine n° 10.124 …") is not credited: the history gives two possible causes.
4. **A change is dated the day the consolidated version applies from**; a different day in the article's history is
   recorded in `Law-in-force:`.
5. **French is the text of the record**; it is the only official language.

## What an AI model did

This repository was built on {today} in **Claude Code**, Anthropic's coding tool, by the model **Claude Opus 5.5**
(model id `claude-opus-5-5`), working from a brief set at Lexifina: a private git history of Monaco law to the
standard of Lexifina's other law records.

The model:

- **Researched the source:** Legimonaco's version addresses and HTML, the terms of reuse, and the prior art below.
- **Wrote all the code and text in this repository:** `tools/build.py`, `tools/reproduce.py`, `tools/check_repo.py`,
  `tools/test_repo.py`, `tools/en_vigueur_au.py`, the README, this file and the licence notice, and chose the design
  described in them.
- **Ran the commands above** and checked the results.

The model did **not**:

- **Write or edit any legal text.** Every word of every article, every date and every act's name and title is copied
  by the script from Legimonaco. The commit messages around them are fixed templates in the script.
- **Take part in building the history.** No AI model is called when the history is built or checked.

The work was not reviewed line by line by a lawyer. Only the Journal de Monaco is authoritative; Legimonaco's
consolidated texts, and so this repository, are not.

## Prior art

Checked {today}: the legalize-dev organisation (github.com/legalize-dev) has no Monaco repository; none of its code or
data is used. No other git history of Monaco law was found.
"""
    (repo / 'REPRODUCE.md').write_text(text, encoding='utf-8', newline='\n')
