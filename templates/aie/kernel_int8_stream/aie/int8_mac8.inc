// Fixed CHARM AIE1 INT8 mac16 selectors; see docs/porting_plan/int8_aie_ml_port.md.
#include <aie_api/aie.hpp>
#include <aie_api/aie_adf.hpp>
#include <aie_api/utils.hpp>

// Eight K terms per output lane. Sign extension to int16 is exact.
// ZOffsets retains the original B selector, including the standalone test layout.
template <unsigned ZOffsets>
static inline aie::accum<acc64, 16> int8_mac8(
    aie::accum<acc64, 16> acc,
    const aie::vector<int8, 64>& a,
    const aie::vector<int8, 32>& b)
{
    static_assert(ZOffsets == 0x88880000 || ZOffsets == 0xCCCC4444 ||
                  ZOffsets == 0x44440000 || ZOffsets == 0xCCCC8888,
                  "Unsupported CHARM INT8 selector");
    aie::unroll_for<unsigned, 0, 8>([&](auto k) __aie_inline {
        aie::vector<int16, 16> x, z;
        aie::unroll_for<unsigned, 0, 16>([&](auto lane) __aie_inline {
            const unsigned r = lane;
            const unsigned t = k;
            const unsigned zi = 2 * ((ZOffsets >> (4 * ((r / 4) * 2 + r % 2))) & 15) + t;
            x.set(static_cast<int16>(a.get(8 * t + r % 8)), r);
            z.set(static_cast<int16>(b.get(zi)), r);
        });
        acc = aie::mac(acc, x, z);
    });
    return acc;
}
