# Monaco law, change by change

Two Monegasque texts as a git repository: the **Constitution of 17 December 1962** (with its 2002 revision) and **loi n° 1.362 du 3 août 2009** on money laundering, terrorist financing and corruption (18 consolidated versions, 2009 to 2025). Each amending act is one commit, credited to that act and dated the day its changes took effect, at noon in Monaco. The text is the French text of [Legimonaco](https://legimonaco.mc), the official legal database of the Principality.

*Français : [plus bas](#français).*

## A lawyer's questions as git commands

| Question | Command |
| --- | --- |
| What did Art. 53 of the Constitution say on 1 January 1990? | `python tools/en_vigueur_au.py 1990-01-01 constitution 53` |
| Art. 22-2 of loi n° 1.362 on 1 January 2022 | `python tools/en_vigueur_au.py 2022-01-01 loi-1362 22-2` |
| The whole of loi n° 1.362 on 1 March 2019 | `python tools/en_vigueur_au.py 2019-03-01 loi-1362` |
| Which law wrote each line of an article? | `git blame constitution/article-53.md` |
| Every change to an article, with the law behind it | `git log -p --follow loi-1362/article-1er.md` |
| Everything one law changed | `git show --stat loi/1549` |
| Every law that changed loi n° 1.362, in order | `git log --reverse --format='%(trailers:key=In-force,valueonly,separator=)%x09%an' -- loi-1362` |
| The state of an act on a day it changed | `git checkout loi-1362/2018-07-07` |
| What no law explains | `git log --grep='^Kind: ' --format='%h%x09%(trailers:key=In-force,valueonly,separator=)%x09%s'` |

The laws with their dates are in [`lois.csv`](lois.csv); each act's articles, with how often each changed, are in its folder's `README.md`. After a rebuild of this repository, refresh old clones with `git fetch --force --tags`.

## The dates, and which one we use

A Monegasque law is dated the day the Prince signs it (`Enacted:`), published in the Journal de Monaco (`Published:`), and enforceable against third parties from the day after its publication (Constitution, Art. 69), unless it provides a later day. **Commits are dated the day the changed text applies from**: the date Legimonaco gives the consolidated version (`<text>@YYYY.MM.DD`), which decides which text governs a case. Where an article's own history gives its change another day ("modifié à compter du …") than the version that prints it, the commit keeps that day in `Law-in-force:`.

**Git cannot store dates before 1970.** The Constitution's text of 17 December 1962 is dated 1970-01-01; its real day is in the `In-force:` trailer and the tag `constitution/1962-12-17`. `tools/en_vigueur_au.py` reads `In-force:`, so it gives the right text for any day.

## How it is checked

`tools/check_repo.py` reads every one of the 20 versions back from git on the day it applies from and compares each file, byte for byte, with the text rebuilt from that version's Legimonaco page, then compares the whole act word for word with the page read independently of the parser. `tools/test_repo.py` checks blame, the reader before and after known amendments, `git log --follow`, the tags, the trailers, the authors and every command in the table above. The build is deterministic: rebuilt from the same data, it gives the same commit hashes. See [`REPRODUCE.md`](REPRODUCE.md).

## What "author" means

The author of a commit is the act that made the change, named as Legimonaco names it (`Loi n° 1.462 du 28 juin 2018`), at an address that cannot exist (`loi-1462@legimonaco.invalid`). So `git blame` names, for each line, the law that last wrote it. Each article in each Legimonaco version carries a "Historique de consolidation" naming the acts that created, amended or repealed it, often with the day ("remplacé à compter du 30 septembre 2023 par la loi n° 1.549 …"). A change is credited to the one act that history names for that day, or to the one act it names for the first time (`Evidence:` in each commit says which).

The first texts are by the acts themselves. Changes no single act explains are by `Legimonaco` and labelled: `Kind: typesetting` where only spacing changed, `Kind: reverted` where a version prints an earlier text again, `Kind: unexplained` otherwise, including where the history names a law and an ordonnance souveraine jointly for one change. Only the documentation commit is by Lexifina.

## What it does not show

- Division headings (Titre, Chapitre, Section; they are in each act's `README.md`), histories and editorial notes.
- The 1911 Constitution, which Legimonaco has only as a PDF attached to the 1962 text, and any act beyond these two.
- Text as amended between two of Legimonaco's versions: the record has exactly the versions Legimonaco publishes, including its own corrections and its versions that print a change early or print an earlier text again (see `REPRODUCE.md`).

This is a research aid. Only the Journal de Monaco is authoritative; the consolidated texts on Legimonaco, and so this repository, are not.

## How it is built

`tools/build.py` reads Legimonaco's list of versions and each version's page, compares consecutive versions article by article, credits each change, and writes the commits. No AI model takes part in building or checking it. Every step, command and decision is in [`REPRODUCE.md`](REPRODUCE.md). `corpus.json` describes the corpus for Lexifina's global index.

## Licence

Source : Legimonaco, base de données juridique officielle de la Principauté de Monaco (Gouvernement Princier), https://legimonaco.mc. Under the Monegasque law on copyright, "Les lois, ordonnances, arrêtés, décisions et publications administratives, judiciaires ou officielles ne bénéficient pas de la protection instituée par la présente loi" (Loi n° 491 du 24 novembre 1948, article 38). The texts were converted to one file per article and arranged as commits; the wording was not changed. Lexifina's own contributions are CC0. See [`LICENSE`](LICENSE).

---

## Français

Deux textes monégasques en dépôt git : la **Constitution du 17 décembre 1962** (révisée en 2002) et la **loi n° 1.362 du 3 août 2009** relative à la lutte contre le blanchiment de capitaux, le financement du terrorisme et la corruption.

- **Chaque commit est un texte modificatif**, inscrit comme auteur : `git blame` montre quelle loi a écrit chaque alinéa.
- **Chaque commit porte la date d'effet de la version consolidée de Legimonaco**, à midi à Monaco. La date de 1962 est ramenée au 1er janvier 1970 ; la vraie date est dans `In-force:`.
- **Un fichier par article**, une ligne par alinéa ou par point.
- **Ce qu'aucun texte n'explique est étiqueté**, jamais attribué à une loi.

Seul le Journal de Monaco fait foi.
