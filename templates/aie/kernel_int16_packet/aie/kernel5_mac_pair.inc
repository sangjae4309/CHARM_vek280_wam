// Rendered into each kernel source by Jinja; no extra generated header is needed.
#include <aie_api/aie.hpp>
#include <aie_api/aie_adf.hpp>

// Replacement for this kernel's fixed AIE1 mac16 selector pattern only:
// xstart=0, xoffsets=0x73727170/0x77767574, xsquare=0x3120,
// zoffsets=0/0, zstep=1. A holds two consecutive K cols, 16 rows each.
// For lane r: acc[r] += A[r]*B[Z] + A[16+r]*B[Z+1].
// Keep each call at the original point in the load/MAC schedule.
template <unsigned Z>
static inline aie::accum<acc64, 16> mm5_mac_pair(
    aie::accum<acc64, 16> acc,
    const aie::vector<int16, 32>& buf_matA,
    const aie::vector<int16, 16>& buf_matB)
{
    static_assert(Z <= 14 && Z % 2 == 0, "Expected an aligned K pair in B");
    acc = aie::mac(acc, buf_matA.extract<16>(0), buf_matB[Z]);
    return aie::mac(acc, buf_matA.extract<16>(1), buf_matB[Z + 1]);
}
