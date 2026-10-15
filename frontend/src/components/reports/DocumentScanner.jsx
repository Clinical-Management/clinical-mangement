import { useEffect, useRef, useState } from 'react'
import { primaryButton, secondaryButton } from '../ui'
import { detectCorners, warpAndEnhance } from './scanner'

const HANDLE = 22

/**
 * Photo of a printed report -> auto-detected page corners (draggable) -> flattened, enhanced copy.
 * Calls onDone({ original: File, processed: Blob }) - the original photo is passed on untouched.
 */
export default function DocumentScanner({ file, onDone, onCancel }) {
  const [bitmap, setBitmap] = useState(null)
  const [corners, setCorners] = useState(null)
  const [enhance, setEnhance] = useState(true)
  const [preview, setPreview] = useState(null) // canvas data URL after processing
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const stage = useRef(null)
  const drag = useRef(null)
  const result = useRef(null)

  useEffect(() => {
    let cancelled = false
    createImageBitmap(file)
      .then((bmp) => {
        if (cancelled) return
        setBitmap(bmp)
        setCorners(detectCorners(bmp))
      })
      .catch(() => setError('This photo could not be opened. Please try again.'))
    return () => {
      cancelled = true
    }
  }, [file])

  if (error) return <p className="text-sm text-red-600">{error}</p>
  if (!bitmap || !corners) return <p className="text-sm text-slate-500">Finding the page...</p>

  // Display scale: fit the photo into the stage width
  const maxW = Math.min(560, window.innerWidth - 48)
  const scale = Math.min(maxW / bitmap.width, 640 / bitmap.height)
  const dw = bitmap.width * scale, dh = bitmap.height * scale

  const onPointerDown = (i) => (e) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    drag.current = i
  }
  const onPointerMove = (e) => {
    if (drag.current == null) return
    const rect = stage.current.getBoundingClientRect()
    const x = Math.min(bitmap.width, Math.max(0, (e.clientX - rect.left) / scale))
    const y = Math.min(bitmap.height, Math.max(0, (e.clientY - rect.top) / scale))
    setCorners((cs) => cs.map((c, j) => (j === drag.current ? [x, y] : c)))
  }

  const process = () => {
    setBusy(true)
    // let the "Processing" state paint before the heavy work
    setTimeout(() => {
      const canvas = warpAndEnhance(bitmap, corners, enhance)
      canvas.toBlob(
        (blob) => {
          result.current = blob
          setPreview(canvas.toDataURL('image/jpeg', 0.6))
          setBusy(false)
        },
        'image/jpeg',
        0.92,
      )
    }, 30)
  }

  if (preview) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-slate-600">Check that the whole report is visible and readable.</p>
        <img src={preview} alt="Scanned report" className="max-h-[70vh] rounded-lg border border-slate-200" />
        <div className="flex flex-wrap gap-2">
          <button type="button" className={secondaryButton} onClick={() => setPreview(null)}>
            Adjust corners
          </button>
          <button type="button" className={primaryButton} onClick={() => onDone({ original: file, processed: result.current })}>
            Use this scan
          </button>
        </div>
      </div>
    )
  }

  const points = corners.map(([x, y]) => `${x * scale},${y * scale}`).join(' ')

  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">Drag the corners to the edges of the report if needed.</p>
      <div
        ref={stage}
        className="relative touch-none select-none"
        style={{ width: dw, height: dh }}
        onPointerMove={onPointerMove}
        onPointerUp={() => (drag.current = null)}
      >
        <canvas
          className="absolute inset-0 rounded-lg"
          width={dw}
          height={dh}
          ref={(c) => c?.getContext('2d').drawImage(bitmap, 0, 0, dw, dh)}
        />
        <svg className="absolute inset-0" width={dw} height={dh}>
          <polygon points={points} fill="rgba(3,149,131,0.15)" stroke="#039583" strokeWidth="2" />
        </svg>
        {corners.map(([x, y], i) => (
          <div
            key={i}
            role="slider"
            aria-label={`Corner ${i + 1}`}
            aria-valuenow={Math.round(x)}
            onPointerDown={onPointerDown(i)}
            className="absolute cursor-grab rounded-full border-2 border-white bg-accent-600 shadow"
            style={{ width: HANDLE, height: HANDLE, left: x * scale - HANDLE / 2, top: y * scale - HANDLE / 2 }}
          />
        ))}
      </div>
      <label className="flex items-center gap-2 text-sm text-slate-700">
        <input type="checkbox" checked={enhance} onChange={(e) => setEnhance(e.target.checked)} />
        Enhance (whiter paper, darker text)
      </label>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={secondaryButton} onClick={onCancel}>
          Retake
        </button>
        <button type="button" className={primaryButton} disabled={busy} onClick={process}>
          {busy ? 'Processing...' : 'Crop and enhance'}
        </button>
      </div>
    </div>
  )
}
