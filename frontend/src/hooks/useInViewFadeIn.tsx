import React, { useRef, useState, useEffect, CSSProperties } from 'react'

export interface FadeInOptions {
  threshold?: number
  rootMargin?: string
  initialY?: number
  transition?: string
}

/**
 * Hook: useInViewFadeIn
 * Detects when an element scrolls into view and fades/translates it in.
 *
 * @param options.threshold    IntersectionObserver threshold (default 0.1)
 * @param options.rootMargin   IntersectionObserver rootMargin (default '0px')
 * @param options.initialY     Start translateY(px) (default 20)
 * @param options.transition   CSS transition string (default 'opacity 0.6s ease-out, transform 0.6s ease-out')
 * @returns { ref, style }     ref: assign to element; style: spread into element’s style
 */
export default function useInViewFadeIn({
  threshold = 0.1,
  rootMargin = '0px',
  initialY = 20,
  transition = 'opacity 0.6s ease-out, transform 0.6s ease-out',
}: FadeInOptions = {}) {
  const ref = useRef<HTMLElement | null>(null)
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    if (!ref.current) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true)
          observer.unobserve(entry.target)
        }
      },
      { threshold, rootMargin }
    )
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [threshold, rootMargin])

  const style: CSSProperties = {
    opacity: isVisible ? 1 : 0,
    transform: isVisible ? 'translateY(0)' : `translateY(${initialY}px)`,
    transition,
  }

  return { ref, style }
}
