"""Freeze independent ESCI and disclosed synthetic OFF case packs."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from approv.harness.casepacks import esci_pack,off_stress_pack,write_pack


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--esci-directory',default='data/cache/public-shopping/esci')
    parser.add_argument('--off-source',default='data/cache/off_india_raw.json')
    parser.add_argument('--output',required=True)
    a=parser.parse_args();root=Path(a.output);root.mkdir(parents=True,exist_ok=True)
    for name,make in [('esci',lambda:esci_pack(Path(a.esci_directory))),('synthetic',lambda:off_stress_pack(Path(a.off_source)))]:
        if (root/(name+'.json')).exists():raise FileExistsError(root/(name+'.json'))
        pack=make();write_pack(root/(name+'.json'),pack);print(name,len(pack['tasks']),flush=True)
