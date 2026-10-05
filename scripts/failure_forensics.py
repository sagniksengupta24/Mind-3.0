#!/usr/bin/env python3
"""Classify preserved Mind 3.0 benchmark failures without fabricating EDA/model results."""
from __future__ import annotations
import argparse, csv, json, re, shutil
from collections import Counter
from pathlib import Path

CATS=("SPECIFICATION_ERROR","INTERFACE_ERROR","SYNTAX_ERROR","TYPE_WIDTH_ERROR","CLOCK_RESET_ERROR","SIMULATION_FAILURE","FORMAL_FAILURE","REPAIR_FAILURE","ENVIRONMENT_FAILURE","OTHER")

def classify(row: dict, log_text: str) -> str:
    fc=(row.get('failure_class') or '').upper()
    failed=(row.get('failure_category') or '').upper()
    text=(log_text or '').lower()
    # Root cause is based on the failing Mind 3.0 stage, not the external benchmark verdict.
    if fc == 'GATE2_INFRASTRUCTURE_FAILURE' or 'unsupported_formal_property' in failed or 'unsupported formal property' in text:
        return 'ENVIRONMENT_FAILURE'
    if 'out is not a valid l-value' in text:
        return 'INTERFACE_ERROR'
    if 'width' in text or 'bit width' in text or 'range' in text:
        return 'TYPE_WIDTH_ERROR'
    if 'reset' in text or 'clock' in text or 'posedge' in text or 'negedge' in text:
        return 'CLOCK_RESET_ERROR'
    if failed == 'RESPONSE_PARSE_FAILURE' or fc == 'MODEL_GENERATION_FAILURE':
        return 'OTHER'
    if 'syntax error' in text or 'errors in port declarations' in text:
        return 'SYNTAX_ERROR'
    if 'mismatch' in text or 'simulation failed' in text or 'simulation failure' in text:
        return 'SIMULATION_FAILURE'
    if 'formal' in failed or ('formal' in text and 'unsupported' not in text):
        return 'FORMAL_FAILURE'
    if 'repair' in text or 'repair' in fc:
        return 'REPAIR_FAILURE'
    if fc == 'SPECIFICATION_ERROR' or failed == 'SPECIFICATION_ERROR':
        return 'SPECIFICATION_ERROR'
    return 'OTHER'

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--p6',type=Path,default=Path('artifacts/P6/results.csv'))
    ap.add_argument('--logs',type=Path,default=Path('artifacts/P6/logs'))
    ap.add_argument('--output',type=Path,default=Path('artifacts/forensics/p6_failure_distribution.json'))
    ap.add_argument('--sample-size',type=int,default=20)
    args=ap.parse_args()
    rows=list(csv.DictReader(args.p6.open()))
    # deterministic representative sample: first N after sorting by task id
    rows=sorted(rows,key=lambda r:r.get('task_id',''))[:args.sample_size]
    counts=Counter(); classified=[]
    for r in rows:
        log=(args.logs/(str(r.get('task_id'))+'.log'))
        text=log.read_text(errors='replace') if log.exists() else ''
        cat=classify(r,text); counts[cat]+=1
        classified.append({'task_id':r.get('task_id'),'benchmark_verdict':r.get('benchmark_verdict'),'mind3_signoff':r.get('mind3_signoff'),'original_failure_class':r.get('failure_class'),'original_failure_category':re.search(r'Failed Category:\s*(.*)',text).group(1).strip() if re.search(r'Failed Category:\s*(.*)',text) else None,'classified_category':cat,'log_path':str(log) if log.exists() else None})
    report={'sample_size':len(rows),'classification_taxonomy':list(CATS),'distribution':dict(counts),'tasks':classified,'source':'preserved prior real EDA run; not a new benchmark result'}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(report,indent=2)+'\n')
    (args.output.parent/'p6_representative_logs').mkdir(exist_ok=True)
    for item in classified:
        if item['log_path']:
            src=Path(item['log_path']); shutil.copy2(src,args.output.parent/'p6_representative_logs'/src.name)
    print(json.dumps(report,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
