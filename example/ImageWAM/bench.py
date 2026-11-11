"""Parameter validation and integer references for the five ImageWAM cases.

All model-dependent values are explicit. Missing values fail closed. Host
reference execution is not an AIE/PL timing measurement.
"""
import argparse
import hashlib
import json
import math
import re
import shutil
from pathlib import Path

import numpy as np


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def required(obj, key):
    if key not in obj or obj[key] is None:
        raise ValueError(f'Missing parameter: {key}')
    return obj[key]


def requant(x, spec, bits):
    """Explicit integer multiplier/right shift, rounding, saturation policy."""
    mul = int(required(spec, 'multiplier'))
    shift = int(required(spec, 'shift'))
    rounding = required(spec, 'rounding')
    overflow = required(spec, 'overflow')
    if not 0 <= shift <= 31 or abs(mul) > 65535:
        raise ValueError('Require shift 0..31 and abs(multiplier) <= 65535')
    y = np.asarray(x, dtype=np.int64) * mul
    if rounding == 'floor':
        y = y >> shift
    elif rounding == 'toward_zero':
        y = np.sign(y) * (np.abs(y) >> shift)
    else:
        raise ValueError('rounding must be floor or toward_zero')
    low, high = -(1 << (bits-1)), (1 << (bits-1))-1
    if overflow == 'saturate':
        y = np.clip(y, low, high)
    elif overflow == 'reject':
        if np.any((y < low) | (y > high)):
            raise ValueError(f'Requantization exceeds signed INT{bits}')
    else:
        raise ValueError('overflow must be saturate or reject')
    return y.astype({8: np.int8, 16: np.int16}[bits])


def hardswish(x, spec):
    """Qf x -> Qf HardSwish, divide truncates toward zero explicitly."""
    frac = int(required(spec, 'fraction_bits'))
    if not 0 <= frac <= 12:
        raise ValueError('HardSwish fraction_bits must be 0..12')
    if required(spec, 'division_rounding') != 'toward_zero':
        raise ValueError('HardSwish implementation requires toward_zero division')
    x = np.asarray(x, dtype=np.int64)
    bound = 6 << frac
    product = x * np.clip(x + (3 << frac), 0, bound)
    return (np.sign(product) * (np.abs(product) // bound)).astype(np.int16)


def rmsnorm(x, gamma, spec):
    """Match the selected isolated INT16 norm.cpp, including integer sqrt+1."""
    scale = int(required(spec, 'scale_i'))
    shift = int(required(spec, 'shift_i'))
    bias = int(required(spec, 'bias_i'))
    if not 0 <= scale <= 15 or not 0 <= shift <= 31:
        raise ValueError('RMSNorm requires scale_i 0..15 and shift_i 0..31')
    if not -32768 <= bias <= 32767:
        raise ValueError('RMSNorm bias_i exceeds INT16')
    x = np.asarray(x, dtype=np.int64)
    mean_sq = np.sum(x*x, axis=-1, dtype=np.int64) // x.shape[-1]
    root = np.fromiter((math.isqrt(int(v)+1) for v in mean_sq.flat),
                       dtype=np.int64).reshape(mean_sq.shape)
    inv = (1 << (2*scale)) // np.maximum(root, 1)
    v = x * np.asarray(gamma, dtype=np.int64)[:, None, :] * inv[..., None]
    if np.any((v < -(1 << 47)) | (v >= (1 << 47))):
        raise ValueError('RMSNorm 48-bit intermediate overflows; revise parameters')
    return np.clip((v >> shift) + bias, -32768, 32767).astype(np.int16)


def rope(x, cs):
    """Adjacent-pair RoPE using externally supplied [cos,sin] Q7 values."""
    x = np.asarray(x, dtype=np.int64)
    cs = np.asarray(cs, dtype=np.int64)
    y = np.empty_like(x)
    even, odd = x[..., 0::2], x[..., 1::2]
    c, s = cs[..., 0::2], cs[..., 1::2]
    y[..., 0::2] = (even*c - odd*s) >> 7
    y[..., 1::2] = (even*s + odd*c) >> 7
    return np.clip(y, -32768, 32767).astype(np.int16)


def load_inputs(case, cfg, params):
    path = Path(required(params, 'input_npz'))
    if not path.is_absolute():
        path = case/path
    # Loaded arrays are never mutated; model data remains owned by the user.
    with np.load(path, allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files}
    for key, shape in cfg['inputs'].items():
        if key not in arrays or list(arrays[key].shape) != shape:
            raise ValueError(f'Input {key}: require shape {shape}')
        dtype = np.bool_ if key == 'mask' else (
            np.int16 if cfg['name'] in ('mlp_branch', 'headsplit_rope') else np.int8)
        if arrays[key].dtype != dtype:
            raise ValueError(f'Input {key}: require dtype {np.dtype(dtype)}')
    return arrays


def validate(case, cfg, p):
    required(p, 'provenance')
    name = cfg['name']
    a = load_inputs(case, cfg, p)
    if cfg['mm']:
        specs = required(p, 'mm_output_requantization')
        for stage, *_ in cfg['mm']:
            # QK is narrowed to an INT16 score, not INT8 probabilities.
            requant(np.array([0]), required(specs, stage), 16 if stage == 'qk' else 8)
    if name == 'mlp_branch':
        hardswish(np.array([0], dtype=np.int16), required(p, 'hardswish'))
        requant(np.array([0]), required(p, 'gate_requantization'), 16)
    if name == 'headsplit_rope':
        norm = required(p, 'rmsnorm')
        for k in ('gamma_q', 'gamma_k'):
            if k not in a or a[k].shape != (24,128) or a[k].dtype != np.int16:
                raise ValueError(f'{k}: require INT16 [24,128]')
        if 'rope_cs' not in a or a['rope_cs'].shape != (417,128) or a['rope_cs'].dtype != np.int16:
            raise ValueError('rope_cs: require INT16 [417,128], interleaved cos/sin in Q7')
        if required(required(p, 'rope'), 'pairing') != 'adjacent' or p['rope']['fraction_bits'] != 7:
            raise ValueError('Selected isolated RoPE requires adjacent pairs and Q7 tables')
        rmsnorm(np.zeros((24,1,128),dtype=np.int16),a['gamma_q'],norm)
    if name == 'self_attention':
        c = required(p, 'consmax')
        for k in ('base','beta','gamma','score_scale','weight_scale','table_provenance'):
            required(c, k)
        if c['base'] not in ('e','2') or float(c['gamma']) <= 0:
            raise ValueError('ConSmax requires base e/2 and positive gamma')
        lut = a.get('consmax_lut')
        if lut is None or lut.shape != (65536,) or lut.dtype != np.int16 or np.any(lut < 0):
            raise ValueError('consmax_lut: require nonnegative INT16 [65536], indexed by score+32768')
        requant(np.array([0]), required(c, 'to_int8'), 8)
    return a


def reference(case, cfg, p, a):
    name = cfg['name']
    out = {}
    if name in ('gu_linear','qkv_linear'):
        for stage, *_ in cfg['mm']:
            acc = a['x'].astype(np.int32) @ a['w'+stage].astype(np.int32)
            out[stage+'_acc32'] = acc
            out[stage] = requant(acc,p['mm_output_requantization'][stage],8)
    elif name == 'mlp_branch':
        out['activation'] = hardswish(a['g'],p['hardswish'])
        out['gated'] = requant(out['activation'].astype(np.int64)*a['u'],p['gate_requantization'],16)
    elif name == 'headsplit_rope':
        for key in ('q','k','v'):
            heads = a[key].reshape(417,24,128).transpose(1,0,2).copy()
            if key == 'v':
                out['v_heads'] = heads
            else:
                y = rmsnorm(heads,a['gamma_'+key],p['rmsnorm'])
                out[key+'_rope'] = rope(y,a['rope_cs'][None,...])
    else:
        out['qk_acc32'] = a['q'].astype(np.int32) @ a['k'].astype(np.int32).T
        scores = requant(out['qk_acc32'],p['mm_output_requantization']['qk'],16)
        weights = a['consmax_lut'][scores.astype(np.int32)+32768].copy()
        weights[~a['mask']] = 0
        out['weights_int16'] = weights
        out['p'] = requant(weights,p['consmax']['to_int8'],8)
        out['pv_acc32'] = out['p'].astype(np.int32) @ a['v'].astype(np.int32)
        out['attention'] = requant(out['pv_acc32'],p['mm_output_requantization']['pv'],8)
    np.savez(case/'reference.npz',**out)
    write_json(case/'reference_status.json',dict(status='host_reference_only',
        parameters_sha256=hashlib.sha256((case/'parameters.json').read_bytes()).hexdigest(),
        shapes={k:list(v.shape) for k,v in out.items()},hardware_latency=None))


def plan(cfg):
    return dict(name=cfg['name'],scope=cfg['scope'],inputs=cfg['inputs'],
                outputs=cfg['outputs'],mm=[dict(stage=n,M=m,K=k,N=o,macs=m*k*o,
                tile=[32,64,32],cascade= min(8,math.ceil(k/64)),
                padded_M=math.ceil(m/32)*32,padded_N=math.ceil(o/32)*32)
                for n,m,k,o in cfg['mm']],
                timing_status='not_measured',clock_assumptions=None)


def prepare_mlp(case, cfg, p, arrays):
    if cfg['name'] != 'mlp_branch':
        raise ValueError('prepare-pl currently supports mlp_branch only')
    part = str(required(p, 'pl_part'))
    clock = float(required(p, 'pl_clock_ns'))
    if not re.fullmatch(r'[A-Za-z0-9_-]+',part) or not math.isfinite(clock) or clock <= 0:
        raise ValueError('Invalid explicit PL part/clock')
    reference(case,cfg,p,arrays)  # Includes range/overflow checks, before synthesis.
    data=case/'data'; data.mkdir(exist_ok=True)
    for k in ('g','u'):
        arrays[k].astype('<i2').tofile(data/(k+'.bin'))
    with np.load(case/'reference.npz',allow_pickle=False) as z:
        z['gated'].astype('<i2').tofile(data/'expected.bin')
    src=case/'src'; src.mkdir(exist_ok=True)
    templates=Path(__file__).resolve().parent/'templates'
    for file in ('mlp.cpp','mlp_tb.cpp'):
        shutil.copy2(templates/file,src/file)
    shutil.copy2(templates/'mlp_hls.tcl',case/'run_hls.tcl')
    hs=p['hardswish']; gate=p['gate_requantization']
    (src/'config.h').write_text('\n'.join([
        '#pragma once',
        '#define CASE_PATH '+json.dumps(str(case)),
        '#define HS_FRAC '+str(int(hs['fraction_bits'])),
        '#define GATE_MULTIPLIER '+str(int(gate['multiplier'])),
        '#define GATE_SHIFT '+str(int(gate['shift'])),
        '#define GATE_TOWARD_ZERO '+str(int(gate['rounding']=='toward_zero')),
        ''
    ]))
    (case/'hls_settings.tcl').write_text(
        f'set imagewam_part {{{part}}}\nset imagewam_clock_ns {clock}\n')
    write_json(case/'preparation_status.json',dict(status='prepared_not_run',
        parameters_sha256=hashlib.sha256((case/'parameters.json').read_bytes()).hexdigest(),
        note='No vendor tool invoked. Compile/co-sim results are not board timing.'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('plan','validate','reference','prepare-pl'))
    parser.add_argument('--case',required=True,type=Path)
    args=parser.parse_args()
    case=args.case.resolve()
    cfg=read_json(case/'config.json')
    if args.command=='plan':
        result=plan(cfg)
        write_json(case/'plan.json',result)
        print(json.dumps(result,indent=2))
        return
    params=read_json(case/'parameters.json')
    try:
        arrays=validate(case,cfg,params)
        if args.command=='reference':
            reference(case,cfg,params,arrays)
        elif args.command=='prepare-pl':
            prepare_mlp(case,cfg,params,arrays)
        print('PASS:',args.command,'(host only; no timing measurement)')
    except (ValueError,KeyError,FileNotFoundError) as exc:
        parser.exit(2,str(exc)+'\n')


if __name__=='__main__':
    main()
