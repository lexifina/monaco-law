"""Checks the git repository against the official text: every version of every act on Legimonaco, read back from git
with tools/en_vigueur_au.py's lookup on the day it applies from, must equal that version's consolidated text.

    python -X utf8 scripts/monaco-law/check_repo.py [--repo ../monaco-law] [--no-record]

Two checks per version, from the cached Legimonaco pages (no network):
1. File by file: the act's files in git on that day are exactly the files the build's parser makes from that version's
   page (same set of files, same bytes).
2. Word for word: the whole act printed in en_vigueur_au.py's order, with its markdown marks removed, has the same
   words in the same order as the official page, read independently of the parser: the title, the preamble, and the
   text of every article section with its "Article N" heading, without the histories ("Historique de consolidation"),
   the editorial note markers and the page's buttons. A section left with nothing but its heading (a repealed
   article) is skipped.
The result is written to verification.json next to this script (unless --no-record), for REPRODUCE.md.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from lxml import html as lhtml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402

TOKEN = re.compile(r'\w+|[^\w\s]')
BLOCKS = {'p', 'li', 'ul', 'ol', 'div', 'section', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br', 'table', 'tr', 'td', 'th',
          'blockquote', 'span'}
DROP_CLASSES = {'title_tools', 'histo', 'histoLink', 'note', 'tooltip_ref', 'editoNote_ref', 'tooltip_a'}


def text_without(e) -> str:
    """Every text node under e, except those inside dropped elements."""
    parts = []

    def walk(x):
        if not isinstance(x.tag, str):
            return
        cls = set((x.get('class') or '').split())
        if cls & DROP_CLASSES or x.tag in ('sup', 'script', 'style', 'button'):
            return
        block = x.tag in BLOCKS
        parts.append((' ' if block else '') + (x.text or ''))
        for c in x:
            walk(c)
            parts.append(c.tail or '')
        if block:
            parts.append(' ')
    walk(e)
    return ''.join(parts).replace(' ', ' ')


def official_words(raw: bytes) -> list[str]:
    doc = lhtml.fromstring(raw)
    content = doc.get_element_by_id('content')
    words = TOKEN.findall(text_without(content.find('.//h1')))
    for c in content:
        if isinstance(c.tag, str) and c.tag == 'section' and (c.get('class') or '').split() == ['block']:
            words += TOKEN.findall(text_without(c))
    for sec in content.iter('section'):
        if 'art' not in (sec.get('class') or '').split():
            continue
        w = TOKEN.findall(text_without(sec))
        head = TOKEN.findall(text_without(next(c for c in sec if isinstance(c.tag, str))))
        if w[len(head):]:
            words += w
    return words


def repo_words(text: str) -> list[str]:
    lines = [re.sub(r'^\s*(#+ |- )', '', l) for l in text.split('\n')]
    return TOKEN.findall(' '.join(lines))


def files_at(repo: str, commit: str, slug: str) -> dict[str, str]:
    """The act's files at a commit, read with one ls-tree and one cat-file --batch (not one git show per file)."""
    out = subprocess.run(['git', 'ls-tree', '-r', commit, f'{slug}/'], cwd=repo, capture_output=True,
                         text=True, encoding='utf-8').stdout.split('\n')
    blobs = []
    for line in out:
        if not line:
            continue
        info, f = line.split('\t', 1)
        if f.endswith('.md') and not f.endswith('/README.md'):
            blobs.append((f[len(slug) + 1:], info.split()[2]))
    if not blobs:
        return {}
    data = subprocess.run(['git', 'cat-file', '--batch'], cwd=repo, input=''.join(f'{sha}\n' for _, sha in blobs).encode(),
                          capture_output=True).stdout
    res, pos = {}, 0
    for name, _ in blobs:
        nl = data.index(b'\n', pos)
        size = int(data[pos:nl].split()[2])
        res[name] = data[nl + 1:nl + 1 + size].decode('utf-8')
        pos = nl + 1 + size + 1
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', default=str(build.ROOT.parent / 'monaco-law'))
    ap.add_argument('--no-record', action='store_true')
    args = ap.parse_args()
    sys.path.insert(0, str(Path(args.repo) / 'tools'))
    import en_vigueur_au as reader
    versions = files = bad = words = wbad = 0
    per_act = {}
    for act in build.ACTS:
        for day in build.version_days(act, offline=True):
            raw = build.fetch(build.version_url(act, day), offline=True)
            parsed = build.read_version(raw)
            expected = {build.file_name(k): build.render(u) for k, u in parsed['units'].items() if u['lines']}
            commit = reader.commit_on(day, act['slug'], cwd=args.repo)
            got = files_at(args.repo, commit, act['slug']) if commit else {}
            versions += 1
            per_act[act['slug']] = per_act.get(act['slug'], 0) + 1
            files += len(expected)
            if got != expected:
                bad += 1
                diff = sorted(set(got) ^ set(expected)) or [k for k in expected if got.get(k) != expected[k]]
                print(f'MISMATCH {act["slug"]} {day}: {diff[:5]}')
            words += 1
            whole = '\n'.join(got[f] for f in sorted(got, key=reader.order))
            ow, rw = official_words(raw), repo_words(whole)
            if ow != rw:
                wbad += 1
                i = next((i for i, (a, b) in enumerate(zip(ow, rw)) if a != b), min(len(ow), len(rw)))
                print(f'WORDS {act["slug"]} {day}: official {len(ow)} vs repo {len(rw)} words; first difference at '
                      f'{i}: {" ".join(ow[max(0, i - 6):i + 6])!r} / {" ".join(rw[max(0, i - 6):i + 6])!r}')
    tip = subprocess.run(['git', 'rev-parse', 'main~1'], cwd=args.repo, capture_output=True, text=True).stdout.strip()
    print(f'{versions} versions checked ({files} files), {bad} mismatches; {words} versions word for word, {wbad} mismatches')
    print('per act:', per_act)
    if not args.no_record:
        p = HERE / 'verification.json'
        rec = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
        rec['check'] = {'versions': versions, 'files': files, 'mismatches': bad, 'wordcheck': words,
                        'word_mismatches': wbad, 'per_act': per_act, 'history_tip': tip}
        p.write_text(json.dumps(rec, indent=1, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    raise SystemExit(1 if bad or wbad else 0)


if __name__ == '__main__':
    main()
