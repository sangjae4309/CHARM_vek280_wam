"""Dependency scheduling around CHARM's fixed-array, multi-workload search.

This maps MM compute regions, not a compiled graph or measured end-to-end time.
Non-MM nodes retain dependencies but have unknown duration and no placement.
"""
from collections import Counter
from dataclasses import dataclass
from math import prod, ceil

import numpy as np
from CDSE.cdse import cdse_top
from CDSE.devices import device_resources


@dataclass(eq=False)
class Tensor:
    name: str
    shape: tuple
    kind: str
    inputs: tuple = ()
    pool: str = ''
    mkn: tuple = ()
    heads: int = 1
    rhs_transposed: bool = False
    rhs_shape: tuple = ()


class Graph:
    def __init__(self):
        self.nodes = []

    def input(self, name, array):
        return self.op(name, 'input', (), array.shape)

    def op(self, name, kind, inputs, shape=None):
        tensor = Tensor(name, tuple(shape or inputs[0].shape), kind, tuple(inputs))
        self.nodes.append(tensor)
        return tensor

    def mm(self, name, lhs, rhs, pool='linear', transpose_rhs=False, heads=1):
        k, n = rhs.shape[-2:]
        if transpose_rhs:
            k, n = n, k
        m, lhs_k = lhs.shape[-2:]
        assert lhs_k == k, (name, lhs.shape, rhs.shape)
        assert heads == 1 or (lhs.shape[0] == rhs.shape[0] == heads)
        inputs = (lhs, rhs) if isinstance(rhs, Tensor) else (lhs,)
        tensor = Tensor(name, (*lhs.shape[:-2], m, n), 'mm', inputs,
                        pool, (m, k, n), heads, transpose_rhs, tuple(rhs.shape))
        self.nodes.append(tensor)
        return tensor


def search_array(nodes, cols, tiles):
    """One fixed ABC/XYZ configuration serves ALL assigned MM shapes."""
    counts = Counter(n.mkn for n in nodes)
    workload = np.array([(*shape, count) for shape, count in counts.items()])
    m, k, n = workload[0, :3]
    config, model = cdse_top(np.zeros((m, k), np.int8), np.zeros((k, n), np.int8),
                            device='vek280', workload=workload, aie_only=True,
                            resource_limits={'aie_cols': cols, 'aie_num': tiles},
                            return_details=True)
    return dict(config=config, model=model,
                costs=dict(zip(counts, model['cycles_per_invocation'])))


def schedule(graph, arrays, split, overlap):
    """Insertion-order list schedule; 24 heads are one synchronized MM batch."""
    finish = {}
    available = dict.fromkeys(arrays, 0)
    serial_finish = 0
    events = []
    for node in graph.nodes:
        ready = max((finish[p] for p in node.inputs), default=0)
        engines = ()
        duration = 0
        if node.kind == 'mm':
            if node.pool == 'head':
                engines = tuple(f'head_{h}' for h in range(node.heads))
            else:
                engines = ('mlp' if split and node.pool == 'mlp' else 'linear',)
            ready = max(ready, *(available[e] for e in engines))
            if not overlap:
                ready = max(ready, serial_finish)
            duration = arrays[engines[0]]['costs'][node.mkn]
            for engine in engines:
                available[engine] = ready + duration
            serial_finish = max(serial_finish, ready + duration)
        finish[node] = ready + duration
        events.append(dict(name=node.name, kind=node.kind, shape=node.shape,
                           inputs=tuple(p.name for p in node.inputs), engines=engines,
                           start=ready, end=finish[node],
                           unknown_duration=node.kind not in ('input', 'mm')))
    return events


def map_graph(graph, head_budgets=(4, 8), splits=(None, 0.5)):
    """Enumerate explicit region candidates, then compare serial/fork schedules.

    head_budgets and splits define the candidate set, not a global optimum.
    No graph/data input is read from files. No vendor tools are invoked.
    """
    resources = device_resources('vek280')
    assert len({n.name for n in graph.nodes}) == len(graph.nodes)
    seen = set()
    for n in graph.nodes:
        assert all(p in seen for p in n.inputs), n.name
        seen.add(n)
    head_nodes = [n for n in graph.nodes if n.pool == 'head']
    assert head_nodes and all(n.heads == 24 for n in head_nodes)
    candidates = []
    cache = {}
    for head_budget in head_budgets:
        head = search_array(head_nodes, resources['aie_cols'], head_budget)
        width = head['model']['placement_width']
        height = head['model']['placement_height']
        heads_per_col = resources['aie_rows'] // height
        head_cols = ceil(24 / heads_per_col) * width
        linear_cols = resources['aie_cols'] - head_cols
        for split in splits:
            if linear_cols < (4 if split is not None else 2):
                continue
            regions = [('linear', 0, linear_cols)]
            if split is not None:
                first_cols = int(linear_cols * split)
                regions = [('linear', 0, first_cols),
                           ('mlp', first_cols, linear_cols - first_cols)]
            arrays = {}
            for pool, col, cols in regions:
                nodes = [n for n in graph.nodes if n.kind == 'mm' and n.pool != 'head'
                         and (split is None or ('mlp' if n.pool == 'mlp' else 'linear') == pool)]
                key = (pool, cols, split is not None)
                if key not in cache:
                    cache[key] = search_array(nodes, cols, cols * resources['aie_rows'])
                array = cache[key]
                config = array['config'].copy()
                config[0, 16] += col
                arrays[pool] = dict(array, config=config)
            for h in range(24):
                config = head['config'].copy()
                config[0, 16] = linear_cols + (h // heads_per_col) * width
                config[0, 17] = (h % heads_per_col) * height
                arrays[f'head_{h}'] = dict(head, config=config)
            occupied = set()
            for array in arrays.values():
                col, row = array['config'][0, 16:18].astype(int)
                w, h = array['model']['placement_width'], array['model']['placement_height']
                rectangle = {(c, r) for c in range(col, col+w) for r in range(row, row+h)}
                assert col >= 0 and row >= 0 and col+w <= 38 and row+h <= 8
                assert not occupied.intersection(rectangle)
                occupied.update(rectangle)
            for overlap in (False, True):
                events = schedule(graph, arrays, split is not None, overlap)
                candidates.append(dict(head_budget=head_budget, split=split,
                    overlap=overlap, arrays=arrays, occupied_tiles=len(occupied),
                    mm_service_makespan=max(e['end'] for e in events), schedule=events))
    best = min(candidates, key=lambda c: (c['mm_service_makespan'], c['occupied_tiles']))
    # Consumers identify values that must survive across branches/layers/steps.
    last_use = {e['name']: e['end'] for e in best['schedule']}
    for event in best['schedule']:
        for parent in event['inputs']:
            last_use[parent] = max(last_use[parent], event['end'])
    lifetimes = [dict(name=e['name'], shape=e['shape'], elements=prod(e['shape']),
                      produced=e['end'], last_consumer_end=last_use[e['name']])
                 for e in best['schedule']]
    return dict(best=best, candidates=candidates, buffer_lifetimes=lifetimes,
                unplaced_operations=[n.name for n in graph.nodes if n.kind not in ('input', 'mm')],
                scope='AIE MM placement and dependency schedule; non-MM costs omitted',
                packed_int4_supported=False, performance_calibrated=False,
                routing_verified=False, complete_graph_feasible=None,
                measured_latency=None)
