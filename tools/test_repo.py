"""Functional smoke test of the built Monaco law repository. Standard library only.

    python -X utf8 scripts/monaco-law/test_repo.py [--repo ../monaco-law] [--no-record]

It clones the repository into a temporary folder (so nothing in --repo is touched) and asserts that:
- `git blame` on a changed provision names the amending law as author;
- tools/en_vigueur_au.py gives the right text before and after known amendments (including a pre-1970 day);
- `git log --follow` on an article lists the amending laws in date order;
- every tag resolves to a commit, and every history commit has an `In-force:` trailer that git parses;
- no commit is authored by Lexifina except the documentation commit;
- every git or python command in the README's table of questions runs without error.
The result is written to verification.json next to this script (unless --no-record), for REPRODUCE.md.
"""
import argparse
import json
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def run(cwd, *args, check=True) -> str:
    out = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, encoding='utf-8')
    if check and out.returncode:
        raise AssertionError(f'{" ".join(args)} failed: {out.stderr.strip()}')
    return out.stdout


def tests(repo: str) -> list[tuple[str, callable]]:
    py = sys.executable
    on = lambda day, act, art: run(repo, py, 'tools/en_vigueur_au.py', day, act, art)
    out = []

    def blame():
        lines = run(repo, 'git', 'blame', '--line-porcelain', 'constitution/article-53.md').split('\n')
        authors = [l[len('author '):] for l in lines if l.startswith('author ')]
        assert 'Loi n° 1.249 du 2 avril 2002' in authors, authors
        assert 'Constitution du 17 décembre 1962' in authors, authors
    out.append(('git blame on Constitution Art. 53 names Loi n° 1.249 du 2 avril 2002 for the lines it changed', blame))

    def on_date_constitution():
        before, after = on('1965-06-01', 'constitution', '53'), on('2002-04-06', 'constitution', '53')
        assert 'dix-huit membres' in before and 'vingt-quatre' not in before, before
        assert 'vingt-quatre membres' in after and 'dix-huit membres' not in after, after
        assert on('2002-04-05', 'constitution', '53') == before
    out.append(('en_vigueur_au: Constitution Art. 53 has 18 members on 1965-06-01 and 2002-04-05 (pre-1970, clamped), 24 from 2002-04-06', on_date_constitution))

    def on_date_law():
        before, after = on('2016-12-09', 'loi-1362', '1er'), on('2016-12-10', 'loi-1362', '1er')
        assert 'multi family office' not in before, before
        assert 'multi family offices' in after, after
        gone = subprocess.run([py, 'tools/en_vigueur_au.py', '2023-09-30', 'loi-1362', '67-3'], cwd=repo,
                              capture_output=True, text=True, encoding='utf-8')
        assert gone.returncode and 'not in force' in gone.stderr, gone
        assert on('2023-09-29', 'loi-1362', '67-3').startswith('# Article 67-3')
    out.append(('en_vigueur_au: loi n° 1.362 Art. 1er gains multi family offices on 2016-12-10 (loi n° 1.439); Art. 67-3 is repealed from 2023-09-30', on_date_law))

    def follow():
        log = run(repo, 'git', 'log', '--follow', '--reverse',
                  '--format=%an%x09%(trailers:key=In-force,valueonly,separator=)', '--', 'loi-1362/article-1er.md')
        rows = [l.split('\t') for l in log.strip().split('\n')]
        days = [d for _, d in rows]
        assert days == sorted(days), days
        laws = [a for a, _ in rows if a.startswith(('Loi', 'Ordonnance'))]
        for want in ('Loi n° 1.362 du 3 août 2009', 'Loi n° 1.439 du 2 décembre 2016', 'Loi n° 1.462 du 28 juin 2018',
                     'Loi n° 1.491 du 23 juin 2020', 'Loi n° 1.528 du 7 juillet 2022', 'Loi n° 1.537 du 9 décembre 2022'):
            assert want in laws, (want, laws)
        assert [laws.index(x) for x in ('Loi n° 1.439 du 2 décembre 2016', 'Loi n° 1.462 du 28 juin 2018', 'Loi n° 1.491 du 23 juin 2020')] \
            == sorted(laws.index(x) for x in ('Loi n° 1.439 du 2 décembre 2016', 'Loi n° 1.462 du 28 juin 2018', 'Loi n° 1.491 du 23 juin 2020'))
    out.append(('git log --follow on loi n° 1.362 Art. 1er lists its amending laws in in-force order', follow))

    def tags():
        names = run(repo, 'git', 'tag').split()
        assert len(names) > 10, names
        for t in names:
            run(repo, 'git', 'rev-parse', '--verify', '-q', f'{t}^{{commit}}')
        for t in names:
            m = re.fullmatch(r'(constitution|loi-1362)/(\d{4}-\d{2}-\d{2})', t)
            if m:
                body = run(repo, 'git', 'log', '-1', '--format=%B', t)
                assert f'In-force: {m.group(2)}' in body, t
    out.append(('every tag resolves to a commit, and each day tag points at a commit in force that day', tags))

    def trailers():
        hashes = run(repo, 'git', 'log', '--format=%H', 'main').split()
        for h in hashes[1:]:
            msg = run(repo, 'git', 'log', '-1', '--format=%B', h)
            parsed = subprocess.run(['git', 'interpret-trailers', '--parse'], cwd=repo, input=msg, capture_output=True,
                               text=True, encoding='utf-8').stdout
            assert re.search(r'^In-force: \d{4}-\d{2}-\d{2}$', parsed, re.M), (h, parsed)
        doc = run(repo, 'git', 'log', '-1', '--format=%s', hashes[0])
        assert doc.startswith('Documentation'), doc
    out.append(('every history commit has an In-force trailer that git interpret-trailers parses (the documentation commit carries none)', trailers))

    def authors():
        rows = run(repo, 'git', 'log', '--format=%H%x09%an%x09%ae%x09%cn%x09%ce', 'main').strip().split('\n')
        lex = [r for r in rows if r.split('\t')[2] == 'monaco-law@lexifina.com']
        assert len(lex) == 1 and lex[0] == rows[0], lex
        assert all(r.split('\t')[3:] == ['Lexifina', 'monaco-law@lexifina.com'] for r in rows)
        assert all(r.split('\t')[2].endswith('@legimonaco.invalid') for r in rows[1:])
    out.append(('no commit is authored by Lexifina except the documentation commit; every committer is Lexifina', authors))

    def readme():
        text = (Path(repo) / 'README.md').read_text(encoding='utf-8')
        cmds = [c for c in re.findall(r'\| `([^`]+)` \|', text) if c.startswith(('git ', 'python '))]
        assert len(cmds) >= 8, cmds
        for c in cmds:
            args = shlex.split(c)
            if args[0] == 'python':
                args[0] = py
            if args[:2] == ['git', 'checkout']:
                args += ['-q']
            res = subprocess.run(args, cwd=repo, capture_output=True, text=True, encoding='utf-8')
            assert res.returncode == 0 and (res.stdout.strip() or args[:2] == ['git', 'checkout']), (c, res.stderr)
        run(repo, 'git', 'checkout', '-q', 'main')
    out.append(('every command in the README table runs and prints a result', readme))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', default=str(ROOT.parent / 'monaco-law'))
    ap.add_argument('--no-record', action='store_true')
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    head = run(args.repo, 'git', 'rev-parse', 'main~1').strip()   # the history tip: stable across documentation rebuilds
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        clone = str(Path(tmp) / 'clone')
        run(tmp, 'git', 'clone', '-q', '--no-hardlinks', str(Path(args.repo).resolve()), clone)
        run(clone, 'git', 'fetch', '-q', '--force', '--tags')
        for name, fn in tests(clone):
            try:
                fn()
                ok = True
            except AssertionError as e:
                ok = False
                print(f'   {e}'[:600])
            print(f'{"PASS" if ok else "FAIL"}: {name}')
            results.append([name, ok])
        import os
        for f in Path(tmp).rglob('*'):
            os.chmod(f, 0o700)
    print(f'{sum(ok for _, ok in results)} of {len(results)} passed against {head}')
    if not args.no_record:
        p = HERE / 'verification.json'
        rec = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
        rec['smoke'] = {'results': results, 'head': head}
        p.write_text(json.dumps(rec, indent=1, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    raise SystemExit(0 if all(ok for _, ok in results) else 1)


if __name__ == '__main__':
    main()
