"""Named template families. Source prefixes preserve existing C++ symbols."""

KERNEL_FAMILIES = {
    'kernel_fp32_stream': {'bytes': 4, 'source_prefix': 'mm0'},
    'kernel_fp32_packet': {'bytes': 4, 'source_prefix': 'mm1'},
    'kernel_int16_packet': {'bytes': 2, 'source_prefix': 'mm5'},
    'kernel_int8_stream': {'bytes': 1, 'source_prefix': 'mm6'},
    'kernel_int8_packet': {'bytes': 1, 'source_prefix': 'mm7'},
}
