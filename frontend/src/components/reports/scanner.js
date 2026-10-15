// Document scanning helpers (pure functions on canvas pixel data, no libraries):
// find the page in a photo, flatten it with a perspective transform, and boost contrast.

/** Otsu's threshold on a greyscale histogram. */
function otsu(grey) {
  const hist = new Array(256).fill(0)
  for (const g of grey) hist[g]++
  const total = grey.length
  let sum = 0
  for (let i = 0; i < 256; i++) sum += i * hist[i]
  let sumB = 0, wB = 0, best = 0, threshold = 127
  for (let t = 0; t < 256; t++) {
    wB += hist[t]
    if (!wB) continue
    const wF = total - wB
    if (!wF) break
    sumB += t * hist[t]
    const mB = sumB / wB, mF = (sum - sumB) / wF
    const between = wB * wF * (mB - mF) ** 2
    if (between > best) [best, threshold] = [between, t]
  }
  return threshold
}

/**
 * Guess the page corners in an image (paper is usually brighter than what it lies on).
 * Returns [tl, tr, br, bl] in source pixel coordinates, falling back to a slight inset.
 */
export function detectCorners(bitmap) {
  const scale = Math.min(1, 600 / Math.max(bitmap.width, bitmap.height))
  const w = Math.round(bitmap.width * scale), h = Math.round(bitmap.height * scale)
  const canvas = new OffscreenCanvas(w, h)
  const ctx = canvas.getContext('2d')
  ctx.drawImage(bitmap, 0, 0, w, h)
  const { data } = ctx.getImageData(0, 0, w, h)
  const grey = new Uint8Array(w * h)
  for (let i = 0; i < grey.length; i++) grey[i] = (data[i * 4] * 0.299 + data[i * 4 + 1] * 0.587 + data[i * 4 + 2] * 0.114) | 0
  const t = otsu(grey)

  // largest bright connected region (4-neighbour flood fill)
  const seen = new Uint8Array(w * h)
  let best = null
  const stack = []
  for (let start = 0; start < grey.length; start++) {
    if (seen[start] || grey[start] <= t) continue
    const region = { size: 0, tl: [0, 0, Infinity], tr: [0, 0, -Infinity], br: [0, 0, -Infinity], bl: [0, 0, Infinity] }
    stack.push(start)
    seen[start] = 1
    while (stack.length) {
      const p = stack.pop()
      const x = p % w, y = (p / w) | 0
      region.size++
      if (x + y < region.tl[2]) region.tl = [x, y, x + y]
      if (x + y > region.br[2]) region.br = [x, y, x + y]
      if (x - y > region.tr[2]) region.tr = [x, y, x - y]
      if (x - y < region.bl[2]) region.bl = [x, y, x - y]
      for (const n of [p - 1, p + 1, p - w, p + w]) {
        if (n < 0 || n >= grey.length || seen[n] || grey[n] <= t) continue
        if ((n === p - 1 && x === 0) || (n === p + 1 && x === w - 1)) continue
        seen[n] = 1
        stack.push(n)
      }
    }
    if (!best || region.size > best.size) best = region
  }

  const inset = (fx, fy) => [bitmap.width * fx, bitmap.height * fy]
  if (!best || best.size < w * h * 0.15) {
    return [inset(0.03, 0.03), inset(0.97, 0.03), inset(0.97, 0.97), inset(0.03, 0.97)]
  }
  return [best.tl, best.tr, best.br, best.bl].map(([x, y]) => [x / scale, y / scale])
}

/** Solve the 8 homography coefficients mapping dst rectangle points -> src quad points. */
function homography(dst, src) {
  const A = [], b = []
  for (let i = 0; i < 4; i++) {
    const [x, y] = dst[i], [u, v] = src[i]
    A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.push(u)
    A.push([0, 0, 0, x, y, 1, -v * x, -v * y]); b.push(v)
  }
  // Gaussian elimination with partial pivoting
  for (let c = 0; c < 8; c++) {
    let pivot = c
    for (let r = c + 1; r < 8; r++) if (Math.abs(A[r][c]) > Math.abs(A[pivot][c])) pivot = r
    ;[A[c], A[pivot]] = [A[pivot], A[c]]
    ;[b[c], b[pivot]] = [b[pivot], b[c]]
    for (let r = 0; r < 8; r++) {
      if (r === c) continue
      const f = A[r][c] / A[c][c]
      for (let k = c; k < 8; k++) A[r][k] -= f * A[c][k]
      b[r] -= f * b[c]
    }
  }
  return b.map((v, i) => v / A[i][i])
}

const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1])

/**
 * Flatten the quad [tl, tr, br, bl] of `bitmap` into an upright page and optionally enhance it.
 * Returns a canvas.
 */
export function warpAndEnhance(bitmap, corners, enhance = true) {
  const [tl, tr, br, bl] = corners
  let outW = Math.max(dist(tl, tr), dist(bl, br))
  let outH = Math.max(dist(tl, bl), dist(tr, br))
  const cap = 2400 / Math.max(outW, outH)
  if (cap < 1) [outW, outH] = [outW * cap, outH * cap]
  outW = Math.round(outW)
  outH = Math.round(outH)

  const src = new OffscreenCanvas(bitmap.width, bitmap.height)
  const sctx = src.getContext('2d')
  sctx.drawImage(bitmap, 0, 0)
  const sdata = sctx.getImageData(0, 0, bitmap.width, bitmap.height).data
  const sw = bitmap.width, sh = bitmap.height

  const [a, b, c, d, e, f, g, h] = homography(
    [[0, 0], [outW, 0], [outW, outH], [0, outH]],
    corners,
  )
  const out = document.createElement('canvas')
  out.width = outW
  out.height = outH
  const octx = out.getContext('2d')
  const img = octx.createImageData(outW, outH)
  const o = img.data

  for (let y = 0; y < outH; y++) {
    for (let x = 0; x < outW; x++) {
      const den = g * x + h * y + 1
      const u = (a * x + b * y + c) / den
      const v = (d * x + e * y + f) / den
      const x0 = Math.min(sw - 2, Math.max(0, u | 0)), y0 = Math.min(sh - 2, Math.max(0, v | 0))
      const fx = Math.min(1, Math.max(0, u - x0)), fy = Math.min(1, Math.max(0, v - y0))
      const i00 = (y0 * sw + x0) * 4, i10 = i00 + 4, i01 = i00 + sw * 4, i11 = i01 + 4
      const k = (y * outW + x) * 4
      for (let ch = 0; ch < 3; ch++) {
        const top = sdata[i00 + ch] * (1 - fx) + sdata[i10 + ch] * fx
        const bot = sdata[i01 + ch] * (1 - fx) + sdata[i11 + ch] * fx
        o[k + ch] = top * (1 - fy) + bot * fy
      }
      o[k + 3] = 255
    }
  }

  if (enhance) {
    // Stretch contrast so the paper becomes white and the ink dark (2nd-98th percentile of luminance)
    const hist = new Array(256).fill(0)
    for (let k = 0; k < o.length; k += 4) hist[(o[k] * 0.299 + o[k + 1] * 0.587 + o[k + 2] * 0.114) | 0]++
    const n = o.length / 4
    let lo = 0, hi = 255, acc = 0
    for (let i = 0; i < 256; i++) if ((acc += hist[i]) >= n * 0.02) { lo = i; break }
    acc = 0
    for (let i = 255; i >= 0; i--) if ((acc += hist[i]) >= n * 0.02) { hi = i; break }
    const range = Math.max(1, hi - lo)
    for (let k = 0; k < o.length; k += 4) {
      for (let ch = 0; ch < 3; ch++) o[k + ch] = Math.min(255, Math.max(0, ((o[k + ch] - lo) * 255) / range))
    }
  }
  octx.putImageData(img, 0, 0)
  return out
}
