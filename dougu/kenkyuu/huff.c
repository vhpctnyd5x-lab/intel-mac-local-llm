// 正準ハフマンの符号化・復号（A1/A3 用）。記号は 0..255、文脈は「1つ前の記号」(nctx=256) か無し (nctx=1)。
// 組み立て: gcc -O2 -shared -fPIC -o huff.so huff.c
#include <stdint.h>
#include <string.h>

// lens: nctx*256 個の符号長（0=使わない、最大30）。codes を正準規則で作る。
static void make_codes(const uint8_t *lens, uint32_t *codes) {
    uint32_t bl_count[32] = {0}, next[32] = {0};
    for (int s = 0; s < 256; s++) bl_count[lens[s]]++;
    bl_count[0] = 0;
    uint32_t code = 0;
    for (int b = 1; b < 32; b++) { code = (code + bl_count[b - 1]) << 1; next[b] = code; }
    for (int s = 0; s < 256; s++) if (lens[s]) codes[s] = next[lens[s]]++;
}

// 返り値: 書いたビット数。out は十分大きい（0 で初期化済み）こと。
int64_t encode(const uint8_t *sym, int64_t n, const uint8_t *lens, int nctx, uint8_t *out) {
    static uint32_t codes[256 * 256];
    for (int c = 0; c < nctx; c++) make_codes(lens + 256 * c, codes + 256 * c);
    uint64_t buf = 0; int nb = 0; int64_t pos = 0, bits = 0; int prev = 0;
    for (int64_t i = 0; i < n; i++) {
        int c = nctx == 1 ? 0 : prev;
        int L = lens[256 * c + sym[i]];
        if (L == 0) return -1;
        buf = (buf << L) | codes[256 * c + sym[i]]; nb += L; bits += L;
        while (nb >= 8) { out[pos++] = (uint8_t)(buf >> (nb - 8)); nb -= 8; }
        prev = sym[i];
    }
    if (nb > 0) out[pos++] = (uint8_t)(buf << (8 - nb));
    return bits;
}

// 正準ハフマンを1ビットずつ読んで復号する。
int64_t decode(const uint8_t *in, int64_t n, const uint8_t *lens, int nctx, uint8_t *sym) {
    static int32_t first[256][32], count[256][32], offs[256][32];
    static uint8_t sorted[256][256];
    for (int c = 0; c < nctx; c++) {
        const uint8_t *l = lens + 256 * c;
        memset(count[c], 0, sizeof count[c]);
        for (int s = 0; s < 256; s++) if (l[s]) count[c][l[s]]++;
        int code = 0, k = 0;
        for (int b = 1; b < 32; b++) {
            code = (code + (b > 1 ? count[c][b - 1] : 0)) << (b > 1 ? 1 : 0);
            if (b == 1) code = 0;
            first[c][b] = code; offs[c][b] = k;
            for (int s = 0; s < 256; s++) if (l[s] == b) sorted[c][k++] = (uint8_t)s;
        }
    }
    int64_t bitpos = 0; int prev = 0;
    for (int64_t i = 0; i < n; i++) {
        int c = nctx == 1 ? 0 : prev;
        int code = 0;
        for (int b = 1; b < 32; b++) {
            code = (code << 1) | ((in[bitpos >> 3] >> (7 - (bitpos & 7))) & 1); bitpos++;
            int d = code - first[c][b];
            if (d >= 0 && d < count[c][b]) { sym[i] = sorted[c][offs[c][b] + d]; goto ok; }
        }
        return -1;
    ok:
        prev = sym[i];
    }
    return bitpos;
}
