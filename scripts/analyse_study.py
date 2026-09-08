"""Describe all checkpointed outcomes; do not silently discard operational failures."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import random
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from approv.harness.shopping import digest,verify_trace
from approv.harness.coverage import wilson
from scripts.run_study import score


def load_records(folder):
    rows=[]
    for path in Path(folder).glob('*.json'):
        if path.name=='manifest.json':continue
        r=json.loads(path.read_text(encoding='utf-8'))
        if 'record_hash' not in r:continue
        if digest({k:v for k,v in r.items() if k!='record_hash'})!=r['record_hash']:raise ValueError('record hash mismatch '+str(path))
        verify_trace(r['result'])
        rows.append(r)
    return rows


def summary(rows,tasks=None):
    groups=defaultdict(list)
    for r in rows:groups[(r['kind'],r['split'],r['result']['binding']['arm'])].append(r)
    output=[]
    for key,records in sorted(groups.items()):
        correct=sum(r['score']['success'] for r in records)
        statuses=Counter(r['result']['status'] for r in records)
        usages=[e['payload'].get('metadata',{}).get('usage',{}) for r in records for e in r['result']['events'] if e['kind'] in ('action','error')]
        errors=Counter(e['payload']['error'] for r in records for e in r['result']['events'] if e['kind']=='error')
        proposals=None
        if tasks is not None:
            proposals=Counter()
            for r in records:
                first=next((e['payload']['action'] for e in r['result']['events']
                    if e['kind']=='action' and e['payload']['action']['type']=='select'),None)
                if first is None:
                    proposals['sessions_without_proposal']+=1
                    continue
                initial=score({'status':'selected','selection':{'product_id':first['product_id'],'units':first['units']}},
                              tasks[r['source_case_id']]['gold'])['success']
                proposals['proposals']+=1
                proposals['correct_first_proposals' if initial else 'incorrect_first_proposals']+=1
                if not initial and r['score']['success']:proposals['incorrect_proposal_to_success']+=1
                if initial and not r['score']['success']:
                    proposals['correct_proposal_to_failed_task']+=1
                    if r['result']['status']=='selected':proposals['correct_proposal_to_wrong_selection']+=1
        output.append(dict(source=key[0],split=key[1],arm=key[2],n=len(records),correct=correct,
            success_rate=correct/len(records),descriptive_wilson=wilson(correct,len(records)),
            status_counts=dict(statuses),wrong_selections=sum(r['result']['status']=='selected' and not r['score']['success'] for r in records),
            mean_actions=sum(r['result']['actions'] for r in records)/len(records),
            mean_session_seconds=sum(r['result']['elapsed_seconds'] for r in records)/len(records),
            mean_interpretation_seconds=sum((r.get('interpretation') or {}).get('elapsed_seconds',0) for r in records)/len(records),
            error_counts=dict(errors),
            proposal_outcomes=dict(proposals) if proposals is not None else None,
            agent_tokens=sum(u.get('total_tokens',0) for u in usages),
            interpretation_tokens=sum((r.get('interpretation') or {}).get('usage',{}).get('total_tokens',0) for r in records),
            invalid_interpretations=sum((r.get('interpretation') or {}).get('status')=='invalid_interpretation' for r in records),
            source_label_counts=dict(Counter(r['score'].get('source_label') for r in records))))
    effects=[]
    for source,split in sorted({(r['kind'],r['split']) for r in rows}):
        cases=defaultdict(dict)
        for r in rows:
            if (r['kind'],r['split'])==(source,split):cases[r['source_case_id']][r['result']['binding']['arm']]=r
        for control in ('baseline','blind_review'):
            paired=[v for v in cases.values() if control in v and 'approv' in v]
            if not paired:continue
            diffs=[int(v['approv']['score']['success'])-int(v[control]['score']['success']) for v in paired]
            clusters=defaultdict(list)
            for v,d in zip(paired,diffs):clusters[v['approv']['case']['cluster']].append(d)
            interval=None
            if len(clusters)>1:
                rng=random.Random(20260908);g=list(clusters.values());samples=[]
                for _ in range(2000):
                    vals=[d for group in rng.choices(g,k=len(g)) for d in group];samples.append(sum(vals)/len(vals))
                samples.sort()
                if samples[49]!=samples[1949]:interval=[samples[49],samples[1949]]
            effects.append(dict(source=source,split=split,control=control,paired_cases=len(paired),
                difference=sum(diffs)/len(diffs),improved=diffs.count(1),regressed=diffs.count(-1),
                unchanged=diffs.count(0),clusters=len(clusters),exploratory_cluster_interval=interval))
    return {'groups':output,'effects':effects,'limitations':[
        'Incomplete schedules are not full experiments. Operational failures remain in denominators.',
        'ESCI scores exact relevance only; quantity and abstention correctness are unlabelled.',
        'Synthetic requests and rule-constructed answers are not human accuracy data.',
        'Related requests share product-name clusters; small template sets cannot establish population accuracy.',
        'Approv interpretation has additional compute cost. No payment or guarantee is tested.']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folders',nargs='+');p.add_argument('--output');p.add_argument('--approv-folder');p.add_argument('--pack')
    a=p.parse_args();rows=[r for folder in a.folders for r in load_records(folder)]
    manifests=[json.loads((Path(f)/'manifest.json').read_text(encoding='utf-8')) for f in a.folders]
    for m in manifests[1:]:
        if any(m.get(k)!=manifests[0].get(k) for k in ('agent','config','adapter','driver_sha256','version')):
            raise ValueError('Do not pool different agents, drivers, configurations or Approv versions')
    group_packs={}
    for folder,m in zip(a.folders,manifests):
        for r in load_records(folder):
            group=(r['kind'],r['split'])
            if group in group_packs and group_packs[group]!=m['pack_hash']:
                raise ValueError('Do not pool different frozen packs within one result group')
            group_packs[group]=m['pack_hash']
    if a.approv_folder:
        base_manifests=[json.loads((Path(f)/'manifest.json').read_text(encoding='utf-8')) for f in a.folders]
        replacement=json.loads((Path(a.approv_folder)/'manifest.json').read_text(encoding='utf-8'))
        for m in base_manifests:
            if any(m[k]!=replacement[k] for k in ('agent','config','pack_hash','split','adapter')):
                raise ValueError('Cannot compare different agents, task packs, surfaces or budgets')
            if m.get('driver_sha256')!=replacement.get('driver_sha256'):
                raise ValueError('Cannot compare different observation driver versions')
        rows=[r for r in rows if r['result']['binding']['arm']!='approv']
        rows += [r for r in load_records(a.approv_folder) if r['result']['binding']['arm']=='approv']
    keys=[(r['kind'],r['source_case_id'],r['result']['binding']['arm']) for r in rows]
    if len(keys)!=len(set(keys)):raise ValueError('Do not pool repeated versions/trials without explicit repeat handling')
    tasks=None
    if a.pack:
        pack=json.loads(Path(a.pack).read_text(encoding='utf-8'))
        if digest({k:v for k,v in pack.items() if k!='content_hash'})!=pack['content_hash']:raise ValueError('pack hash mismatch')
        for folder in a.folders+([a.approv_folder] if a.approv_folder else []):
            if json.loads((Path(folder)/'manifest.json').read_text(encoding='utf-8'))['pack_hash']!=pack['content_hash']:
                raise ValueError('Scoring pack differs from recorded experiment')
        tasks={t['case']['id']:t for t in pack['tasks']}
        for r in rows:
            if score(r['result'],tasks[r['source_case_id']]['gold'])!=r['score']:raise ValueError('Recorded score does not match answer key')
    result=summary(rows,tasks);result['source_folders']=a.folders;result['approv_folder']=a.approv_folder
    result['schedules']=[]
    for folder in a.folders+([a.approv_folder] if a.approv_folder else []):
        manifest=json.loads((Path(folder)/'manifest.json').read_text(encoding='utf-8'))
        completed={(r['source_case_id'],r['result']['binding']['arm']) for r in load_records(folder)}
        result['schedules'].append({'folder':folder,'scheduled':len(manifest['schedule']),
            'completed':len(completed),'missing':[x for x in manifest['schedule'] if tuple(x) not in completed]})
    text=json.dumps(result,indent=2)
    if a.output:Path(a.output).write_text(text+'\n',encoding='utf-8')
    print(text)
