// src/hooks/useScrollClamp.tsx
import { useState, useEffect, RefObject } from 'react'

/**
 * @param ref           — the element to watch
 * @param initialAngle  — starting rotation (in degrees)
 * @param maxDelta      — how much more to rotate (positive or negative)
 * @param startFactor   — fraction of viewport height to begin rotating (0–1), default 0.8
 */
export function useScrollClamp(
  ref: RefObject<HTMLElement>,
  initialAngle: number,
  maxDelta: number,
  startFactor = 0.8
): number {
  const [angle, setAngle] = useState(initialAngle)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    function onScroll() {
      const rect = el.getBoundingClientRect()
      const vh = window.innerHeight
      const startY = vh * startFactor

      if (rect.top > startY) {
        // before trigger point → stay at initialAngle
        setAngle(initialAngle)
      } else if (rect.top < 0) {
        // scrolled past top → clamp at final
        setAngle(initialAngle + maxDelta)
      } else {
        // between startY → 0 : interpolate
        const progress = (startY - rect.top) / startY
        setAngle(initialAngle + progress * maxDelta)
      }
    }

    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [ref, initialAngle, maxDelta, startFactor])

  return angle
}
