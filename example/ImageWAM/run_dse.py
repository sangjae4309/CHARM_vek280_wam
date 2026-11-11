#!/usr/bin/env python3
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from example.ImageWAM.graph_mapping import Graph, map_graph
from example.ImageWAM.generate_design import generate_design

# Direct construction: returned tensors connect each operation to its consumers.
# NumPy weights supply shapes/dtypes, not numerical inference or model parameters.
# The mapping is an INT8 MM baseline; INT4 packing and nonlinear costs are pending.
imagewam = Graph()
image = imagewam.input('image', np.zeros((288, 128), dtype=np.int8))
text = imagewam.input('text_state', np.zeros((129, 7680), dtype=np.int8))
action = imagewam.input('action_noise', np.zeros((16, 14), dtype=np.int8))
cache = {}

# step=-1: prefill once. step=0..9: complete action denoising iterations.
for step in range(-1, 10):
    prefill = step == -1
    phase = 'prefill' if prefill else f'action_{step}'
    width, ff = (3072, 9216) if prefill else (1024, 4096)
    time = imagewam.op(phase + '.time', 'sinusoidal_embedding',
                       () if prefill else (action, prefill_done), (1, 256))
    condition = imagewam.mm(phase + '.time_in', time, np.zeros((256, width), dtype=np.int8))
    condition = imagewam.op(phase + '.time_silu', 'silu', (condition,))
    condition = imagewam.mm(phase + '.time_out', condition, np.zeros((width, width), dtype=np.int8))
    mod = {}
    groups = [('image', 6), ('text', 6), ('single', 3)] if prefill else [('action', 6), ('single', 3), ('head', 2)]
    for group, count in groups:
        c = imagewam.op(phase + '.' + group + '_silu', 'silu', (condition,))
        mod[group] = imagewam.mm(phase + '.' + group + '_mod', c,
                                np.zeros((width, count * width), dtype=np.int8))

    if prefill:
        streams = {
            'text': imagewam.mm('prefill.text_in', text, np.zeros((7680, 3072), dtype=np.int8)),
            'image': imagewam.mm('prefill.image_in', image, np.zeros((128, 3072), dtype=np.int8)),
        }
    else:
        streams = {'action': imagewam.mm(phase + '.input', action, np.zeros((14, 1024), dtype=np.int8))}

    # Layers 0..4: double blocks. Layers 5..24: single blocks.
    for layer in range(25):
        double = layer < 5
        prefix = f'{phase}.layer_{layer}'
        if layer == 5:
            streams = {'single': imagewam.op(prefix + '.join_tokens', 'concat_tokens',
                       tuple(streams.values()), (417 if prefill else 16, width))}
        normalized = {}
        qkv = {'q': [], 'k': [], 'v': []}
        for stream, residual in streams.items():
            tokens = residual.shape[0]
            coefficients = mod[stream if double else 'single']
            x = imagewam.op(prefix + '.' + stream + '.ln', 'layernorm', (residual,))
            x = imagewam.op(prefix + '.' + stream + '.mod', 'modulation', (x, coefficients))
            normalized[stream] = x
            for role in ('q', 'k', 'v'):
                value = imagewam.mm(prefix + '.' + stream + '.' + role, x,
                                    np.zeros((width, 3072), dtype=np.int8))
                value = imagewam.op(value.name + '.heads', 'head_split', (value,), (24, tokens, 128))
                if role != 'v':
                    value = imagewam.op(value.name + '.norm', 'rmsnorm', (value,))
                qkv[role].append(value)

        tokens = 417 if prefill else 16
        q = imagewam.op(prefix + '.q_join', 'concat_tokens', tuple(qkv['q']), (24, tokens, 128))
        k = imagewam.op(prefix + '.k_join', 'concat_tokens', tuple(qkv['k']), (24, tokens, 128))
        v = imagewam.op(prefix + '.v_join', 'concat_tokens', tuple(qkv['v']), (24, tokens, 128))
        q = imagewam.op(prefix + '.q_rope', 'rope', (q,))
        k = imagewam.op(prefix + '.k_rope', 'rope', (k,))
        if prefill:
            cache[layer] = (k, v)
        else:
            prefix_k, prefix_v = cache[layer]
            k = imagewam.op(prefix + '.cache_k_join', 'concat_tokens', (prefix_k, k), (24, 433, 128))
            v = imagewam.op(prefix + '.cache_v_join', 'concat_tokens', (prefix_v, v), (24, 433, 128))
        scores = imagewam.mm(prefix + '.qk', q, k, pool='head', transpose_rhs=True, heads=24)
        scores = imagewam.op(prefix + '.scale_mask', 'scale_and_mask', (scores,))
        p = imagewam.op(prefix + '.consmax', 'consmax_and_requant', (scores,))
        context = imagewam.mm(prefix + '.pv', p, v, pool='head', heads=24)
        context = imagewam.op(prefix + '.merge_heads', 'head_merge', (context,), (tokens, 3072))

        for stream, residual in tuple(streams.items()):
            tokens = residual.shape[0]
            name = prefix + '.' + stream
            coefficients = mod[stream if double else 'single']
            if double:
                part = imagewam.op(name + '.attention_split', 'split_token_rows', (context,), (tokens, 3072))
                part = imagewam.mm(name + '.attention_out', part, np.zeros((3072, width), dtype=np.int8))
                residual = imagewam.op(name + '.attention_residual', 'gated_residual', (residual, part, coefficients))
                x = imagewam.op(name + '.ffn_ln', 'layernorm', (residual,))
                x = imagewam.op(name + '.ffn_mod', 'modulation', (x, coefficients))
            else:
                # Fork: GU uses the same normalized input as QKV, not context.
                x = normalized[stream]
            g = imagewam.mm(name + '.g', x, np.zeros((width, ff), dtype=np.int8), pool='mlp')
            u = imagewam.mm(name + '.u', x, np.zeros((width, ff), dtype=np.int8), pool='mlp')
            g = imagewam.op(name + '.hardswish', 'hardswish', (g,))
            product = imagewam.op(name + '.product', 'multiply_and_requant', (g, u))
            if double:
                output = imagewam.mm(name + '.ffn_down', product,
                                     np.zeros((ff, width), dtype=np.int8), pool='mlp')
            else:
                # Join: output projection waits for both attention and GU branches.
                joined = imagewam.op(name + '.concat', 'concat_features', (context, product), (tokens, 3072 + ff))
                output = imagewam.mm(name + '.out', joined, np.zeros((3072 + ff, width), dtype=np.int8))
            streams[stream] = imagewam.op(name + '.output', 'gated_residual', (residual, output, coefficients))

    if prefill:
        prefill_done = imagewam.op('prefill.done', 'phase_barrier', tuple(streams.values()), (1,))
    else:
        hidden = streams['single']
        hidden = imagewam.op(phase + '.final_ln', 'layernorm', (hidden,))
        hidden = imagewam.op(phase + '.final_mod', 'modulation', (hidden, mod['head']))
        velocity = imagewam.mm(phase + '.velocity', hidden, np.zeros((1024, 14), dtype=np.int8))
        action = imagewam.op(phase + '.euler', 'euler_update', (action, velocity))

output = imagewam.op('action_output', 'fp32_denormalize', (action,))

# Each candidate has 24 simultaneous head engines and shared projection arrays.
# None: one projection array. 0.5: separate linear/MLP col regions.
# CHARM picks one fixed configuration for ALL shapes assigned to each array.
# Serial and dependency-aware fork/join schedules are compared on those arrays.
mapping = map_graph(imagewam, head_budgets=(4, 8), splits=(None, 0.5))
arrays = mapping['best']['arrays']
schedule = mapping['best']['schedule']
buffer_lifetimes = mapping['buffer_lifetimes']
comparison = [(c['head_budget'], c['split'], c['overlap'], c['occupied_tiles'],
               c['mm_service_makespan']) for c in mapping['candidates']]
# Inspect these variables with: python3 -i run_dse.py
# Times are uncalibrated MM service-cycle proxies; non-MM time is unknown.
design = generate_design(imagewam, mapping, Path(__file__).resolve().parents[2] / 'sim/tmp_imagewam_charm_dse_vek280')
print(f"Generated {design['kernel_instances']} MM kernels in {design['aie_dir']}; see mapping.csv and design_status.md")
