#!/usr/bin/env python3
"""Fetch reference datasets at the revisions recorded in data/provenance.json."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = json.loads((ROOT / 'data/provenance.json').read_text())
SOURCES = [
    ('syrnt-source', 'https://github.com/etcbc/syrnt.git', PROVENANCE['peshitta']['commit']),
    ('sycgloss-source', 'https://github.com/celkhaissi/sycgloss.git', PROVENANCE['lexicon']['commit']),
]

def git(folder, *args):
    return subprocess.check_output(['git', '-C', str(folder), *args], text=True).strip()

def main():
    for name, url, revision in SOURCES:
        target = ROOT / 'data' / name
        if target.exists():
            if not (target / '.git').exists():
                raise SystemExit(f'{target} exists without Git provenance; preserve or move it before fetching.')
            if git(target, 'rev-parse', 'HEAD') != revision:
                raise SystemExit(f'{target} is at a different revision; preserve or move it before fetching.')
            if git(target, 'status', '--porcelain'):
                raise SystemExit(f'{target} has local changes; preserve them before fetching.')
            print(f'{name}: pinned revision already present')
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'init', str(target)], check=True)
        git(target, 'remote', 'add', 'origin', url)
        git(target, 'fetch', '--depth=1', 'origin', revision)
        git(target, 'checkout', '--detach', 'FETCH_HEAD')
        print(f'{name}: {revision}')

if __name__ == '__main__':
    main()
