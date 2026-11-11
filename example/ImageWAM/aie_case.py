"""Actual CHARM generator and packet fixtures for isolated ImageWAM MM probes.

Preserves the existing INT8 output interface. Each graph invocation is a
cascade partial, not an implicit full-K reduction or connected attention graph.
"""
import argparse
import json
import math
from pathlib import Path
import shutil

import numpy as np
from CACG.gen_aie import gen_aie_top


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2)+'\n')


def layout(spec):
    name,m,k,n=spec
    b=min(8,math.ceil(k/64))
    passes=math.ceil(k/(64*b))
    return dict(name=name,M=m,K=k,N=n,tile_M=32,tile_K=64,tile_N=32,
                cascade=b,k_passes=passes,
                iterations=math.ceil(m/32)*math.ceil(n/32)*passes)


def generate(case, config, placement):
    cfg=json.loads((case/'config.json').read_text())
    stages=[layout(s) for s in cfg['mm']]
    if len(config)!=len(stages):
        raise ValueError('AIE_config must contain one row per MM stage')
    for row,s in zip(config,stages):
        if list(row)!=[32,64,32,1,s['cascade'],1,1,1,s['cascade'],1,1,'kernel_int8_packet']:
            raise ValueError('AIE_config differs from the packet fixture tile contract')
    repo=Path(__file__).resolve().parents[2]
    data=case/'data'; data.mkdir(exist_ok=True)
    files=[[f'data/{s["name"]}_lhs.txt',f'data/{s["name"]}_rhs.txt'] for s in stages]
    # Regenerate owned source files while preserving the case's input data.
    if (case/'aie').exists(): shutil.rmtree(case/'aie')
    gen_aie_top(str(case),str(repo/'templates/aie')+'/',
                np.asarray(config,dtype=object),np.asarray(placement,dtype=int),
                simulation_iterations=[s['iterations'] for s in stages],
                input_files=files,copy_input_data=False)
    dump(case/'aie_manifest.json',dict(status='source_generated_not_compiled',
        generator='CACG.gen_aie.gen_aie_top',aie_config=np.asarray(config).tolist(),
        placement=np.asarray(placement).tolist(),stages=stages,input_files=files,
        output_files=[f'data/output{i}.txt' for i in range(len(stages))],
        input_bits=8,output_bits=8,plio_bits=128,plio_MHz=230,
        scope='independent MM cascade partials; no PL reduction or ConSmax connection',
        full_operator_latency_measured=False))


def header(pid):
    # Same source row/col fields and odd parity as PL generateHeader().
    h=(31<<16)|(127<<21)|pid
    return h | ((1-(h.bit_count() & 1))<<31)


def write_packet(file, values, pid):
    raw=np.asarray(values,dtype=np.int8).reshape(-1).view(np.uint8)
    if len(raw)%4: raise ValueError('Payload must contain whole 32-bit words')
    words=[header(pid)]+np.frombuffer(raw.tobytes(),dtype='<u4').tolist()
    for i in range(0,len(words),4):
        if i+4>=len(words): file.write('TLAST\n')
        file.write(' '.join(map(str,words[i:i+4]))+'\n')


def tiles(s):
    for r in range(0,s['M'],32):
        for c in range(0,s['N'],32):
            for p in range(s['k_passes']):
                yield r,c,p*64*s['cascade']


def tile(a,r,c,m,n):
    out=np.zeros((m,n),dtype=np.int8)
    sub=a[r:r+m,c:c+n]
    out[:sub.shape[0],:sub.shape[1]]=sub
    return out


def operands(z,s):
    name=s['name']
    if name in ('g','u','q','k','v'):
        a,b=z['x'],z['w'+name]
    elif name=='qk':
        a,b=z['q'],z['k'].T
    else:
        # P is an explicit post-ConSmax/requantization input. Never fabricate it.
        a,b=z['p'],z['v']
    if a.shape!=(s['M'],s['K']) or b.shape!=(s['K'],s['N']):
        raise ValueError(f'{name}: operand shape mismatch')
    if a.dtype!=np.int8 or b.dtype!=np.int8:
        raise ValueError(f'{name}: inputs must be signed INT8')
    return a,b


def prepare_inputs(case, archive):
    manifest=json.loads((case/'aie_manifest.json').read_text())
    with np.load(archive,allow_pickle=False) as z:
        # Preflight every result before emitting any text. With the unchanged
        # INT8 interface, out-of-range partials require a different interface.
        for s in manifest['stages']:
            a,b=operands(z,s)
            for r,c,k in tiles(s):
                part=tile(a,r,k,32,64*s['cascade']).astype(np.int32) @ tile(b,k,c,64*s['cascade'],32).astype(np.int32)
                if np.any((part < -128)|(part > 127)):
                    raise ValueError(f'{s["name"]} tile ({r},{c},{k}) exceeds INT8 output; no silent wrap/saturation. INT32 partial-output support is required for these inputs.')
        for layer,s in enumerate(manifest['stages']):
            a,b=operands(z,s)
            paths=[case/f for f in manifest['input_files'][layer]]
            with paths[0].open('w') as fa, paths[1].open('w') as fb:
                for r,c,k in tiles(s):
                    for stage in range(s['cascade']):
                        aa=tile(a,r,k+stage*64,32,64)
                        bb=tile(b,k+stage*64,c,64,32)
                        write_packet(fa,aa.reshape(4,8,64).transpose(0,2,1).reshape(-1),stage)
                        write_packet(fb,bb.reshape(4,16,32).transpose(0,2,1).reshape(-1),stage)
    dump(case/'input_status.json',dict(status='prepared_range_checked',archive=str(archive.resolve()),
         scope='MM cascade partials only',full_operator_latency=False))


def packets(path):
    current=[]; last=False
    with path.open() as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith(('#','T ')): continue
            if line=='TLAST':
                if last: raise ValueError('Repeated TLAST')
                last=True; continue
            current.extend(int(w,16) if w.lower().startswith('0x') else int(w) for w in line.split())
            if last:
                yield current
                current=[]; last=False
    if current or last: raise ValueError('Unterminated packet')


def check(case,archive):
    manifest=json.loads((case/'aie_manifest.json').read_text())
    report=[]
    with np.load(archive,allow_pickle=False) as z:
        for layer,s in enumerate(manifest['stages']):
            a,b=operands(z,s)
            got=packets(case/'aiesimulator_output'/manifest['output_files'][layer])
            count=0
            for r,c,k in tiles(s):
                pkt=next(got,None)
                if pkt is None or len(pkt)!=257: raise ValueError('Missing/wrong-size output packet')
                raw=np.asarray([w & 0xffffffff for w in pkt[1:]],dtype='<u4').view(np.int8)
                actual=raw.reshape(4,32,8).transpose(0,2,1).reshape(32,32)
                expected=tile(a,r,k,32,64*s['cascade']).astype(np.int32) @ tile(b,k,c,64*s['cascade'],32).astype(np.int32)
                if not np.array_equal(actual,expected): raise ValueError(f'{s["name"]}: output mismatch at {r},{c},{k}')
                count+=1
            if next(got,None) is not None: raise ValueError('Unexpected extra packet')
            report.append(dict(stage=s['name'],packets=count,compared_values=count*1024))
    dump(case/'comparison.json',dict(status='MM_partial_outputs_match',stages=report,
         full_operator_verified=False))


def command(case):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('inputs','check'))
    p.add_argument('--input-npz',required=True,type=Path)
    args=p.parse_args()
    (prepare_inputs if args.action=='inputs' else check)(case,args.input_npz)
