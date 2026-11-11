"""Generate real CHARM MM sources and explicit ImageWAM dispatch/placement files.

No model data or JSON input is read. No numerical interfaces are changed.
The emitted compute graph has logical ADF ports; transport/nonlinear kernels
and wide full-K reduction remain explicit integration requirements.
"""
import csv
from math import ceil
from pathlib import Path
import re

import numpy as np
from CACG.gen_aie import gen_aie_top


def write_csv(path, columns, rows):
    with path.open('w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(columns)
        writer.writerows(rows)


def cpp_string(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def generate_design(graph, mapping, case):
    case = Path(case)
    repo = Path(__file__).resolve().parents[2]
    arrays = mapping['best']['arrays']
    names = list(arrays)
    ids = {name: i for i, name in enumerate(names)}
    nodes = {node: i for i, node in enumerate(graph.nodes)}
    configurations = np.concatenate([arrays[name]['config'] for name in names]).astype(object)
    configurations[:, 15] = np.arange(len(names))
    aie_config = configurations[:, [*range(10), 13, 14]]
    placement = configurations[:, 15:19].copy()
    placement[:, 0] = np.arange(len(names))
    gen_aie_top(str(case), str(repo / 'templates/aie'), aie_config, placement,
                copy_input_data=False, io_mode='ports', graph_names=names, verbose=False)

    tile_rows = []
    array_rows = []
    dispatch = []
    operation_rows = []
    dependencies = []
    iterations = dict.fromkeys(names, 0)
    cpp_dispatch = []
    cpp_operations = []
    schedule_rows = []
    connection_rows = []
    for node, event in zip(graph.nodes, mapping['best']['schedule']):
        node_id = nodes[node]
        assert node.name == event['name']
        dependency_offset = len(dependencies)
        dependencies.extend(nodes[parent] for parent in node.inputs)
        connection_rows.extend((nodes[parent], parent.name, node_id, node.name, slot)
                               for slot, parent in enumerate(node.inputs))
        dispatch_offset = len(dispatch)
        for engine in event['engines']:
            s = arrays[engine]['config'][0]
            m, k, n = node.mkn
            m_tile, k_tile, n_tile = s[:3] * s[3:6]
            mt, kt, nt = ceil(m/m_tile), ceil(k/k_tile), ceil(n/n_tile)
            count = mt * kt * nt
            iterations[engine] += count
            head = int(engine.removeprefix('head_')) if engine.startswith('head_') else -1
            rhs = node.inputs[1].name if len(node.inputs) == 2 else re.sub(r'^action_\d+\.', 'action.', node.name) + '.weight'
            dispatch.append((node_id, node.name, engine, head, m, k, n,
                             mt, kt, nt, mt*m_tile, kt*k_tile, nt*n_tile, count,
                             node.inputs[0].name, rhs, int(node.rhs_transposed),
                             int(kt > 1), 'INT8_cascade_partial'))
            cpp_dispatch.append('    {' + ', '.join(map(str, (node_id, ids[engine], head,
                m, k, n, mt, kt, nt, count, int(node.rhs_transposed), int(kt > 1)))) + '},')
        shape = 'x'.join(map(str, node.shape))
        operation_rows.append((node_id, node.name, node.kind, shape,
                               dependency_offset, len(node.inputs),
                               dispatch_offset, len(dispatch)-dispatch_offset,
                               'MM_cascade_sources' if node.kind == 'mm' else 'not_generated'))
        dims = tuple(node.shape) + (0,) * (3-len(node.shape))
        cpp_operations.append('    {' + ', '.join((cpp_string(node.name), cpp_string(node.kind),
            str(len(node.shape)), '{' + ', '.join(map(str, dims)) + '}',
            str(dependency_offset), str(len(node.inputs)), str(dispatch_offset),
            str(len(dispatch)-dispatch_offset))) + '},')
        schedule_rows.append((node_id, node.name, node.kind, '|'.join(event['engines']),
                              int(event['start']), int(event['end']), int(event['unknown_duration'])))

    ports = []
    cpp_arrays = []
    for name, array in arrays.items():
        layer = ids[name]
        s = configurations[layer]
        h1, w1, w2, a, b, c, ab, cb, pin, pout = s[:10]
        col, row, height = s[16:19]
        width = array['model']['placement_width']
        lhs_ports, rhs_ports, out_ports = a*(c//ab)*(b//pin), c*(a//cb)*(b//pin), a*c//pout
        array_rows.append((layer, name, s[14], h1, w1, w2, a, b, c, ab, cb, pin, pout,
                           col, row, width, height, a*b*c, lhs_ports, rhs_ports, out_ports,
                           iterations[name], f'aie/layer{layer}/aie_top_L{layer}.h'))
        cpp_arrays.append('    {' + ', '.join((cpp_string(name), cpp_string(s[14]),
            ', '.join(str(s[i]) for i in range(22) if i != 14), str(iterations[name]))) + '},')
        for direction, count in (('lhs', lhs_ports), ('rhs', rhs_ports), ('out', out_ports)):
            for port in range(count):
                ports.append((layer, name, direction, port,
                              f'{name}.{direction}[{port}]',
                              pin if direction != 'out' else pout, 'unbound_logical_packet_port'))
        # Match aie_top.h's physical chain order and logical N-chain permutation.
        for ai in range(a):
            for physical_j in range(c):
                chain = ai*c + physical_j
                tile_row = row + chain % height
                anchor = col + (chain//height)*b + ((chain % height) % 2)*(b-1)
                first_col = anchor if tile_row % 2 == 0 else anchor-b+1
                logical_j = physical_j
                if (c//ab) % 2 == 0 and height % 2 == 0:
                    logical_j = physical_j//2 + (c//2+c%2 if physical_j % 2 else 0)
                for stage in range(b):
                    role = 3 if b == 1 else 0 if stage == 0 else 2 if stage == b-1 else 1
                    tile_rows.append((layer, name, ai, logical_j, stage,
                        first_col+stage, tile_row, role,
                        f'mm7_kernel{role}_L{layer}',
                        f'aie/layer{layer}/mm7_kernel{role}_L{layer}.cc',
                        f'{name}.compute.mm_{ai}_{logical_j}.mm[{stage}]'))
    assert len({(r[5], r[6]) for r in tile_rows}) == len(tile_rows)
    assert all(0 <= r[5] < 38 and 0 <= r[6] < 8 for r in tile_rows)

    write_csv(case/'mapping.csv',
        ('array_id','array','kernel_family','tile_M','tile_K','tile_N','A','B','C','A_broadcast','B_broadcast',
         'pack_in','pack_out','col','row','width','height','kernels','lhs_ports','rhs_ports',
         'out_ports','full_model_kernel_iterations','graph_header'), array_rows)
    write_csv(case/'tile_mapping.csv',
        ('array_id','array','M_partition','N_partition','cascade_stage','col','row','kernel_role',
         'kernel_function','source','instance'), tile_rows)
    write_csv(case/'ports.csv',
        ('array_id','array','direction','port','graph_port','packet_ids','binding_status'), ports)
    write_csv(case/'operations.csv',
        ('node_id','operation','kind','output_shape','dependency_offset','dependency_count',
         'dispatch_offset','dispatch_count','source_status'), operation_rows)
    write_csv(case/'connections.csv',
        ('producer_id','producer','consumer_id','consumer','input_slot'), connection_rows)
    write_csv(case/'schedule.csv',
        ('node_id','operation','kind','arrays','proxy_start_cycles','proxy_end_cycles','unknown_duration'), schedule_rows)
    write_csv(case/'mm_dispatch.csv',
        ('node_id','operation','array','head','M','K','N','M_blocks','K_passes','N_blocks',
         'padded_M','padded_K','padded_N','kernel_iterations','lhs_tensor','rhs_tensor_or_weight',
         'rhs_transposed','requires_full_K_reduction','output_contract'), dispatch)
    write_csv(case/'tensor_lifetimes.csv',
        ('tensor','shape','elements','proxy_produced','proxy_last_consumer_end'),
        ((r['name'], 'x'.join(map(str,r['shape'])), r['elements'], int(r['produced']),
          int(r['last_consumer_end'])) for r in mapping['buffer_lifetimes']))
    write_csv(case/'candidates.csv',
        ('head_budget','projection_split','overlap','occupied_tiles','proxy_MM_cycles'),
        ((c['head_budget'], 'shared' if c['split'] is None else c['split'], c['overlap'],
          c['occupied_tiles'], int(c['mm_service_makespan'])) for c in mapping['candidates']))

    # A real C++ data contract for a future runtime; not an empty executor stub.
    header = '''#pragma once
#include <cstddef>
#include <cstdint>

// Generated configuration/data only. No transport or nonlinear executor is supplied.
// INT8 cascade partial outputs require an agreed wide full-K reduction interface.
namespace imagewam_plan {
struct Array {
    const char* name; const char* kernel_family;
    int tile_m, tile_k, tile_n, a, b, c, a_broadcast, b_broadcast, pack_in, pack_out;
    int x, y, z, element_bytes, layer, col, row, height, lhs_buffer, rhs_buffer, out_buffer;
    std::uint64_t total_iterations;
};
struct Operation {
    const char* name; const char* kind; int rank; int shape[3];
    std::uint32_t dependency_offset, dependency_count, dispatch_offset, dispatch_count;
};
struct MMDispatch {
    std::uint32_t node, array; int head;
    int m, k, n, m_blocks, k_passes, n_blocks;
    std::uint64_t iterations; bool rhs_transposed, needs_full_k_reduction;
};
static constexpr Array arrays[] = {
'''
    header += '\n'.join(cpp_arrays) + '\n};\nstatic constexpr Operation operations[] = {\n'
    header += '\n'.join(cpp_operations) + '\n};\nstatic constexpr std::uint32_t dependencies[] = {\n'
    for start in range(0, len(dependencies), 24):
        header += '    ' + ', '.join(map(str, dependencies[start:start+24])) + ',\n'
    header += '};\nstatic constexpr MMDispatch dispatch[] = {\n' + '\n'.join(cpp_dispatch) + '\n};\n'
    header += 'static constexpr std::size_t array_count = sizeof(arrays)/sizeof(arrays[0]);\n'
    header += 'static constexpr std::size_t operation_count = sizeof(operations)/sizeof(operations[0]);\n'
    header += 'static constexpr std::size_t dispatch_count = sizeof(dispatch)/sizeof(dispatch[0]);\n}\n'
    (case/'imagewam_schedule.hpp').write_text(header)
    (case/'aie/include_paths.txt').write_text('aie\n' + ''.join(f'aie/layer{i}\n' for i in range(len(names))))
    total_in = sum(p[2] != 'out' for p in ports)
    total_out = sum(p[2] == 'out' for p in ports)
    (case/'design_status.md').write_text(f'''# Generated ImageWAM compute design

Status: source generated; not target-compiled, simulated or board-validated.

- {len(arrays)} compute arrays, {len(tile_rows)} placed INT8 MM kernel instances.
- `aie/aie_top_all.cpp` and `.h`: separately controllable ADF compute graphs named
  `linear`, `head_0`, ..., `head_23`; no common run count is imposed.
- `aie/include_paths.txt`: source include directories, relative to this case.
- `aie/layer*/`: original CHARM generator's MM kernels, cascade graphs and arrays.
- `mapping.csv` / `tile_mapping.csv`: exact configurations and compute locations.
- `operations.csv` / `connections.csv` / `schedule.csv`: full logical workload and schedule.
- `mm_dispatch.csv`: {len(dispatch)} per-array jobs, padding and repeated K passes.
- `imagewam_schedule.hpp`: C++ configurations, dependency indices and MM dispatch records.
- `tensor_lifetimes.csv`, `ports.csv`, `candidates.csv`: storage requirements, ports and search evidence.

These are real MM kernel and graph sources. The selected graph has {total_in} input
and {total_out} output **logical packet ports**, not allocated physical PLIOs.
The {total_in} input ports exceed VEK280's 112 aggregate 128-bit PLIO ceiling if
bound one-to-one. The top intentionally exposes ADF ports and does not generate
invalid shim constraints, fake fixture data or a standalone simulation main.
Bind a transport graph before treating this as a runnable top-level design.

Numerical behavior is unchanged: INT8 operands and INT8 cascade partial outputs.
INT4 weights, wide multi-pass K reduction, requantization, nonlinear kernels,
physical intermediate/cache storage and runtime transport are not implemented by
this source generation. They remain required for full ImageWAM inference.
Non-MM rows are explicitly `not_generated`; they are not empty replacement kernels.
The schedule's cycle values are uncalibrated MM-only proxies. No inference,
end-to-end latency, routing feasibility or numerical accuracy is claimed.
''')
    return dict(aie_dir=case/'aie', arrays=len(arrays), kernel_instances=len(tile_rows),
                dispatches=len(dispatch), logical_input_ports=total_in,
                logical_output_ports=total_out, status='source_generated_not_compiled')
