"""Export local study evidence and source archives, with a file-hash manifest."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile


def export_study(destination):
    root=Path(__file__).resolve().parents[1]
    study=root/'data/cache/shopping-study'
    files=[p for p in study.rglob('*') if p.is_file() and p.suffix in ('.json','.jsonl','.py')
           and '__pycache__' not in p.parts]
    files += [root/'README.md',root/'pyproject.toml']
    files += list((root/'scripts').glob('*.py'))
    files += list((root/'approv').rglob('*.py'))
    files += list((root/'tests').rglob('*.py'))
    files += [root/'docs'/name for name in ('shopping-harness.md','security.md',
              'direction-2026-09-11.md')]
    files += [root/'docs/archive'/name for name in ('product-requirements.md',
              'shopping-study-results-2026-09-08.md','public-shopping-datasets.md','external-review-2026-09-08.md')]
    files += [root/'docs/decisions'/name for name in ('0017-traceable-shopping-experiments.md',
              '0018-original-requests-and-synthetic-experiments.md')]
    files += [root/'data/cache/public-shopping/esci'/name for name in ('LICENSE','NOTICE','README.md','manifest.json')]
    files=sorted(set(p for p in files if p.is_file()))
    manifest={'created_at':datetime.now(timezone.utc).isoformat(),
              'note':'Local evidence export; file hashes establish consistency, not independent authorship or catalogue truth.',
              'files':{str(p.relative_to(root).as_posix()):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                       'bytes':p.stat().st_size} for p in files}}
    destination=Path(destination)
    if destination.exists() or destination.with_suffix('.manifest.json').exists():
        raise FileExistsError('Use a new bundle filename')
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Source/data snapshots only: no environment files, registry contents or headers.
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for file in files:archive.write(file,file.relative_to(root).as_posix())
        archive.writestr('bundle-manifest.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(destination) as archive:
        for name,entry in manifest['files'].items():
            if hashlib.sha256(archive.read(name)).hexdigest()!=entry['sha256']:
                raise ValueError('Bundle verification failed: '+name)
    destination.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'bundle':str(destination.resolve()),'files':len(files),'bytes':destination.stat().st_size}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination')
    export_study(parser.parse_args().destination)
