// Measurement kernel: full ImageWAM activation/gating, projections excluded.
// config.h is generated only from explicit case parameters.
#include <ap_int.h>
#include <hls_stream.h>
#include "config.h"

typedef ap_uint<512> beat_t;

void imagewam_mlp(hls::stream<beat_t>& g, hls::stream<beat_t>& u,
                  hls::stream<beat_t>& y) {
#pragma HLS INTERFACE axis port=g
#pragma HLS INTERFACE axis port=u
#pragma HLS INTERFACE axis port=y
#pragma HLS INTERFACE ap_ctrl_hs port=return
    for (int i = 0; i < 417 * 9216 / 32; ++i) {
#pragma HLS PIPELINE II=1
        beat_t gv = g.read(), uv = u.read(), result = 0;
        for (int lane = 0; lane < 32; ++lane) {
#pragma HLS UNROLL
            ap_int<16> x = gv.range(16*lane+15,16*lane);
            ap_int<16> other = uv.range(16*lane+15,16*lane);
            ap_int<32> gate = ap_int<32>(x) + (3 << HS_FRAC);
            if (gate < 0) gate = 0;
            if (gate > (6 << HS_FRAC)) gate = 6 << HS_FRAC;
            // Signed division truncates toward zero, matching the reference.
            ap_int<48> act = (ap_int<48>(x) * gate) / (6 << HS_FRAC);
            ap_int<64> product = act * other * GATE_MULTIPLIER;
            ap_int<64> out;
            if (GATE_TOWARD_ZERO && product < 0)
                out = -((-product) >> GATE_SHIFT);
            else
                out = product >> GATE_SHIFT;
            // 'reject' policy is enforced by the pre-run reference check.
            // All accepted values therefore have identical hardware behavior.
            if (out > 32767) out = 32767;
            if (out < -32768) out = -32768;
            result.range(16*lane+15,16*lane) = ap_int<16>(out);
        }
        y.write(result);
    }
}
