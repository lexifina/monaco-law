"""Prints an act, or one article of it, as it stood on a given day, from this repository's history.

    python tools/en_vigueur_au.py 2001-01-01 constitution 53       # Art. 53 of the Constitution on 1 January 2001
    python tools/en_vigueur_au.py 2020-01-01 loi-1362 22-2         # Art. 22-2 of loi n° 1.362 on 1 January 2020
    python tools/en_vigueur_au.py 2024-01-01 loi-1362              # the whole of loi n° 1.362

The act is named by its folder (constitution, loi-1362). The article is its number as printed ("1er", "22-2-1",
"preliminaire"), or "intitule" / "preambule". Every commit carries the day its text applies from in its "In-force:"
trailer. Commits before 1970 are dated 1970-01-01 because git cannot store older dates, so the day is read from the
trailer, never from the commit date. Standard library only.
"""
import datetime as dt
import re
import subprocess
import sys

SUFFIXES = ['', 'bis', 'ter', 'quater', 'quinquies', 'sexies', 'septies', 'octies', 'nonies', 'decies']


def git(*args: str, cwd=None) -> str:
    return subprocess.run(['git', *args], capture_output=True, text=True, encoding='utf-8', check=True, cwd=cwd).stdout


def commit_on(day: str, path: str, cwd=None, branch: str = 'main') -> str | None:
    """The last commit touching `path` whose In-force day is on or before `day` (history is linear and in order)."""
    out = git('log', '--format=%H%x00%(trailers:key=In-force,valueonly,separator=)%x01', branch, '--', path, cwd=cwd)
    for rec in out.split('\x01'):
        rec = rec.strip()
        if not rec:
            continue
        h, d = rec.split('\x00')
        if d.strip() and d.strip() <= day:
            return h
    return None


def order(name: str) -> tuple:
    """The order of an act's files: title, preamble, articles by number (1er, 2, 2-1, 2-1-1, 3 ...)."""
    key = name.rsplit('/', 1)[-1][:-3]
    if key == 'intitule':
        return (0, 0, ())
    if key == 'preambule':
        return (1, 0, ())
    key = key.removeprefix('article-')
    if key == 'preliminaire':
        return (2, 0, ())
    m = re.fullmatch(r'(\d+)(er)?(.*)', key)
    if not m:
        return (4, 0, (key,))
    rest = tuple(int(x) if x.isdigit() else (SUFFIXES.index(x) if x in SUFFIXES else 99) for x in m.group(3).split('-') if x)
    return (3, int(m.group(1)), rest)


def file_for(article: str) -> str:
    a = article.removesuffix('.md')
    return f'{a}.md' if a in ('intitule', 'preambule') or a.startswith('article-') else f'article-{a}.md'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    day, act = sys.argv[1], sys.argv[2].strip('/')
    dt.date.fromisoformat(day)
    branch = 'futur' if day > dt.date.today().isoformat() and git('branch', '--list', 'futur').strip() else 'main'
    commit = commit_on(day, act, branch=branch)
    if not commit:
        sys.exit(f'{act} is not in the record on {day}.')
    if len(sys.argv) > 3:
        name = file_for(sys.argv[3])
        try:
            print(git('show', f'{commit}:{act}/{name}'), end='')
        except subprocess.CalledProcessError:
            sys.exit(f'{act}/{name} was not in force on {day}.')
        return
    files = [f for f in git('ls-tree', '-r', '--name-only', commit, f'{act}/').split('\n')
             if f.endswith('.md') and not f.endswith('/README.md')]
    for f in sorted(files, key=order):
        print(git('show', f'{commit}:{f}'))


if __name__ == '__main__':
    main()
