# How this history was made, and how to make it again

This file records exactly how the repository was built: the sources, the commands, the software, the decisions made
by hand, and what an AI model did and did not do. The build writes it, so it describes the build that made this
commit.

## Short version

```sh
git clone https://github.com/lexifina/monaco-law && cd monaco-law
pip install lxml
python -X utf8 tools/build.py --repo ../rebuilt --today 2026-10-28
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
build read 35 pages.

| What | Where |
| --- | --- |
| Each text's consolidated versions and the day each applies from | `<text>?versions` (JSON: `previousVersions`, `currentVersion`, `nextVersions`) |
| The text of each version | `<text>@YYYY.MM.DD/` (HTML), listed with sha256 in `data/versions.json` |
| Which act created, amended or repealed each article, and from which day | each article's "Historique de consolidation" in that version (`aside.histo`: `<u data-nature data-number data-date>` and the words "à compter du …") |
| Each amending law's title and publication in the Journal de Monaco | the law's own page, `/tnc/loi/YYYY/MM-DD-N.NNN/` ("Publication") |

| Act | Legimonaco | Versions | From | Article changes |
| --- | --- | ---: | --- | ---: |
| Constitution | `https://legimonaco.mc/constitution` | 2 | 1962-12-17 to 2002-04-06 | 16 |
| Loi n° 1.362 | `https://legimonaco.mc/tnc/loi/2009/08-03-1.362` | 18 | 2009-08-08 to 2025-11-22 | 485 |

The data was retrieved on 2026-10-28, one request at a time at least one second apart, with
the user agent `lexifina-watch/1.0 (+https://lexifina.com; corpus@lexifina.com)`.

## The build, step by step

1. `python -X utf8 scripts/monaco-law/build.py` in Lexifina's own repository fetched the pages and wrote this
   repository; every later build ran with `--offline`. `tools/build.py` here is the same file as
   `scripts/monaco-law/build.py` there (git blob `e5f571755743c0f13010a69cbf962d9b134e60f2`), with `tools/reproduce.py`, which writes this file,
   `tools/check_repo.py` and `tools/test_repo.py`. The documentation commit is dated 2026-10-28, the day the data was
   retrieved (the newest file in the cache), not the day of the run.
2. `python -X utf8 scripts/monaco-law/check_repo.py` read every version back from git with
   `tools/en_vigueur_au.py`'s own lookup, on the day it applies from, and compared it with the official page:
   `20 versions checked (2535 files compared byte for byte), 0 mismatches; 20 versions checked word for word against the whole page, 0 mismatches` (against history tip `4a64606d7f3c74a38aeaf08057ae9cab69cb5272`).
   File by file, the act's files on that day must be exactly the files the build's parser makes from that version's
   page. Word for word, the whole act printed by `tools/en_vigueur_au.py`, without its markdown marks, must have the
   same words in the same order as the page read independently of the parser (the text of every article section with
   its "Article N" heading, the title and the preamble, without the histories, notes and buttons).
3. `python -X utf8 scripts/monaco-law/build.py --offline --verify-rebuild` built the repository again from the cache into an empty temporary folder and compared every commit and tag: identical = `true` for 37 history commits and 34 tags (history tip `4a64606d7f3c74a38aeaf08057ae9cab69cb5272`). This documentation commit then records that result, so the same command run on this build compares `main` itself too.
4. `python -X utf8 scripts/monaco-law/test_repo.py` ran the functional smoke test against the built repository
   (standard library only):

   - PASS: git blame on Constitution Art. 53 names Loi n° 1.249 du 2 avril 2002 for the lines it changed
   - PASS: en_vigueur_au: Constitution Art. 53 has 18 members on 1965-06-01 and 2002-04-05 (pre-1970, clamped), 24 from 2002-04-06
   - PASS: en_vigueur_au: loi n° 1.362 Art. 1er gains multi family offices on 2016-12-10 (loi n° 1.439); Art. 67-3 is repealed from 2023-09-30
   - PASS: git log --follow on loi n° 1.362 Art. 1er lists its amending laws in in-force order
   - PASS: every tag resolves to a commit, and each day tag points at a commit in force that day
   - PASS: every history commit has an In-force trailer that git interpret-trailers parses (the documentation commit carries none)
   - PASS: no commit is authored by Lexifina except the documentation commit; every committer is Lexifina
   - PASS: every command in the README table runs and prints a result

   8 of 8 passed (against history tip `4a64606d7f3c74a38aeaf08057ae9cab69cb5272`).

5. `git push -f origin main --tags` published it to GitHub as a private repository.

It ran with Python 3.12.10, lxml 6.1.3 and git version 2.46.0.windows.1 on Windows 11. No network service other than Legimonaco is involved.

## How the text and the commits are derived

Everything below is done by `tools/build.py`, deterministically.

- **Texts.** For each act, every consolidated version Legimonaco lists. The Constitution has two (1962 and the 2002
  revision); loi n° 1.362 has 18, from the text as first in force in 2009.
- **Text of an article.** Each article is one file, `<act>/article-<number>.md` (for example
  `loi-1362/article-22-2-1.md`, `constitution/article-1er.md`). Each paragraph and each list item is one line, list
  items as `- ` at their depth; numbering such as "1°)" is part of the printed words. The act's title is
  `intitule.md` (loi n° 1.362's title was replaced in 2023) and the Constitution's preamble `preambule.md`. Division
  headings (Titre, Chapitre, Section) are listed in each act's `README.md`, not in the history. Histories, editorial
  notes and links are left out. Spacing is collapsed. Nothing else is changed. An article with no text in a version
  (repealed, or kept only as a number) has no file.
- **Changes.** Consecutive versions are compared article by article. 501 article changes were found.
- **Cause.** Each changed article's history in the newer version is read as a list of clauses, each naming an act and,
  where it says so, the day it takes effect ("modifié à compter du 30 septembre 2023 par la loi n° 1.549 …"). The
  change is credited:
  - to the one act whose clause takes effect on the version's day (`Evidence: … history-date`,
    168 article changes);
  - else to the one act the history names that the previous version's history did not (`history`,
    285), or, where it names several, the one of them that appears in the
    whole text for the first time in this version (`history+window`, 3).
  Where nothing credits one act:
  - a change of spacing only is a **typesetting** commit by the publisher (18 article changes);
  - a version that prints again the text of an earlier version, with no new act in the history, is a **reverted**
    commit by the publisher (12);
  - anything else is an **unexplained** commit by the publisher, credited to no act
    (15), including 3 changes whose
    history names a law and an ordonnance souveraine jointly in one clause: two possible causes, so neither is credited.
- **Commits.** One commit per act per amending act per day (19 law commits), one for each act's first text
  (2), 6 typesetting, 3 reverted and 7
  unexplained commits, in the order they took effect, then one for this documentation dated 2026-10-28.
  - The author is the act, named as Legimonaco names it (`Loi n° 1.462 du 28 juin 2018`), at an address that cannot
    exist (`loi-1462@legimonaco.invalid`), so `git blame` names the law. The first texts are by the act itself
    (`Constitution du 17 décembre 1962`, `Loi n° 1.362 du 3 août 2009`). Typesetting, reverted and unexplained commits
    are by `Legimonaco <legimonaco@legimonaco.invalid>`. Only the documentation commit is by Lexifina.
  - Author and committer dates are noon in Monaco (Central European Time, summer time by the European rules, coded in
    the script) on the day the version applies from. The committer is `Lexifina <monaco-law@lexifina.com>`.
  - Git cannot store dates before 1970. The 1 commit(s) before 1970 (the Constitution of 17 December 1962) are
    dated 1970-01-01, one second apart in order, and carry the real day in `In-force:`, in a `Date-note:` and in the
    tags. The reader `tools/en_vigueur_au.py` uses `In-force:`, not the commit date.
  - Trailers: `In-force:` (every commit), `Enacted:` (the act's date), `Published:` (the Journal de Monaco),
    `Law-in-force:` where the article's history gives the change another day than the version that prints it,
    `Evidence:`, `Affecting:`, `Source:` (the law) and `Text:` (the consolidated version), `Kind:` for the labelled
    commits, `Named-in-history:` and `Same-text-as:`.
  - Tags: each act's days (`loi-1362/2023-09-30`) and each amending act's last commit (`loi/1549`); 34 in all.

Changes printed by a version before the day their history gives (credited, with `Law-in-force:`):

- loi-1362 2021-06-05 60: loi/1.503/2020-12-23, history says 2021-12-31
- loi-1362 2021-06-05 60-1: loi/1.503/2020-12-23, history says 2021-12-31
- loi-1362 2021-06-05 61: loi/1.503/2020-12-23, history says 2021-12-31
- loi-1362 2021-06-05 62: loi/1.503/2020-12-23, history says 2021-12-31
- loi-1362 2021-06-05 62-1: loi/1.503/2020-12-23, history says 2021-12-31
- loi-1362 2021-06-05 62-2: loi/1.503/2020-12-23, history says 2021-12-31
- loi-1362 2021-06-05 63: loi/1.503/2020-12-23, history says 2021-12-31
- loi-1362 2021-06-05 63-1: loi/1.503/2020-12-23, history says 2021-12-31
- loi-1362 2021-06-05 64-1: loi/1.503/2020-12-23, history says 2021-08-31
- loi-1362 2021-06-05 64-2: loi/1.503/2020-12-23, history says 2021-08-31
- loi-1362 2021-06-05 64-3: loi/1.503/2020-12-23, history says 2021-08-31
- loi-1362 2021-06-05 64-4: loi/1.503/2020-12-23, history says 2021-08-31
- loi-1362 2021-06-05 64-5: loi/1.503/2020-12-23, history says 2021-08-31
- loi-1362 2021-06-05 64-6: loi/1.503/2020-12-23, history says 2021-08-31
- loi-1362 2022-02-12 64-1: loi/1.503/2020-12-23, history says 2021-08-31
- loi-1362 2022-02-12 64-2: loi/1.503/2020-12-23, history says 2021-08-31
- loi-1362 2022-02-12 64-3: loi/1.503/2020-12-23, history says 2021-08-31
- loi-1362 2022-02-12 64-4: loi/1.503/2020-12-23, history says 2021-08-31
- loi-1362 2022-02-12 64-5: loi/1.503/2020-12-23, history says 2021-08-31
- loi-1362 2022-02-12 64-6: loi/1.503/2020-12-23, history says 2021-08-31

Typesetting commits:

- loi-1362 2021-06-05: 1er, 4-1, 5, 32, 44, 49
- loi-1362 2021-08-31: 1er, 4-1, 32, 44, 49
- loi-1362 2021-12-31: 64-2
- loi-1362 2022-02-12: 4-1, 32, 44, 50
- loi-1362 2022-07-23: 50
- loi-1362 2023-08-12: 4

Reverted commits:

- loi-1362 2021-08-31: 42, 60, 60-1, 61, 62, 62-1, 62-2, 63, 63-1
- loi-1362 2021-12-31: 16, 22-2
- loi-1362 2023-08-12: 22-2

Unexplained commits:

- constitution 2002-04-06: 49
- loi-1362 2021-06-05: 23
- loi-1362 2021-08-31: 16, 22-2, 64-1, 64-2, 64-3, 64-4, 64-5, 64-6
- loi-1362 2023-08-11: 46-1, 46-5
- loi-1362 2023-08-12: 16
- loi-1362 2023-09-30: 75
- loi-1362 2024-03-02: 64-7

## Decisions made by hand

These choices were made when the tool was written, after looking at the data. They are in the code.

1. **The acts.** The Constitution of 17 December 1962, with its one revision (loi n° 1.249 du 2 avril 2002), and loi
   n° 1.362 du 3 août 2009 on money laundering, terrorist financing and corruption: still in force, amended by 13
   acts in 17 later versions, and Legimonaco has its text as first in force. The
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

This repository was built on 2026-10-28 in **Claude Code**, Anthropic's coding tool, by the model **Claude Opus 5.5**
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

Checked 2026-10-28: the legalize-dev organisation (github.com/legalize-dev) has no Monaco repository; none of its code or
data is used. No other git history of Monaco law was found.
