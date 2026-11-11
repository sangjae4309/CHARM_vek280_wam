#include <ap_int.h>
#include <hls_stream.h>
#include <fstream>
#include <iostream>
#include <cstdint>
#include "config.h"
typedef ap_uint<512> beat_t;
void imagewam_mlp(hls::stream<beat_t>&, hls::stream<beat_t>&, hls::stream<beat_t>&);

static bool read16(std::ifstream& file, int16_t& value) {
    unsigned char b[2];
    if (!file.read(reinterpret_cast<char*>(b),2)) return false;
    value = static_cast<int16_t>(unsigned(b[0]) | unsigned(b[1]) << 8);
    return true;
}

int main() {
    std::ifstream gf(CASE_PATH "/data/g.bin",std::ios::binary);
    std::ifstream uf(CASE_PATH "/data/u.bin",std::ios::binary);
    std::ifstream ef(CASE_PATH "/data/expected.bin",std::ios::binary);
    if (!gf || !uf || !ef) return 2;
    hls::stream<beat_t> g,u,y;
    constexpr int beats=417*9216/32;
    for (int i=0;i<beats;++i) {
        beat_t gv=0,uv=0;
        for(int j=0;j<32;++j) {
            int16_t a,b;
            if (!read16(gf,a) || !read16(uf,b)) return 3;
            gv.range(j*16+15,j*16)=ap_int<16>(a);
            uv.range(j*16+15,j*16)=ap_int<16>(b);
        }
        g.write(gv); u.write(uv);
    }
    imagewam_mlp(g,u,y);
    unsigned mismatches=0;
    std::ofstream actual(CASE_PATH "/data/actual.bin",std::ios::binary);
    if (!actual) return 4;
    for(int i=0;i<beats;++i) {
        beat_t v=y.read();
        for(int j=0;j<32;++j) {
            int16_t expected;
            if (!read16(ef,expected)) return 3;
            ap_int<16> got=v.range(j*16+15,j*16);
            if (got.to_int()!=expected) ++mismatches;
            uint16_t raw=static_cast<uint16_t>(got.to_int());
            actual.put(raw & 255); actual.put(raw >> 8);
        }
    }
    if (!g.empty() || !u.empty() || !y.empty()) return 5;
    if (gf.peek()!=EOF || uf.peek()!=EOF || ef.peek()!=EOF) return 6;
    std::cout << "Compared " << beats*32 << " values; mismatches=" << mismatches << '\n';
    return mismatches ? 1 : 0;
}
