"""Archive code before an experiment so concurrent development cannot alter replay."""
import argparse
from pathlib import Path
import shutil


def freeze(destination):
    root=Path(__file__).resolve().parents[1]
    destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError(destination)
    destination.mkdir(parents=True)
    shutil.copytree(root/'approv',destination/'approv',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    script=(root/'scripts/run_study.py').read_text(encoding='utf-8')
    script=script.replace('Path(__file__).resolve().parents[1]','Path(__file__).resolve().parent')
    (destination/'run_study.py').write_text(script,encoding='utf-8')
    return destination/'run_study.py'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination')
    print(freeze(parser.parse_args().destination))
