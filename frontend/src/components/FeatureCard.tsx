// src/components/FeatureCard.tsx
import React from 'react'

export interface FeatureCardProps {
  /** Any SVG/Icon element (e.g. from react-icons) */
  icon: React.ReactNode
  /** The title string, e.g. "SAFE ACCOUNTS, EASY SCHEDULING" */
  title: string
  /** The body copy under the title */
  description: string
  /** Optional wrapper classes (e.g. for width or transforms) */
  className?: string
  /** dark = transparent + white border + white text; 'light' = white bg + gray border + dark text */
  variant?: 'dark' | 'light'
}

const FeatureCard: React.FC<FeatureCardProps> = ({
  icon,
  title,
  description,
  className = '',
  variant = 'dark',
}) => {
    const isDark = variant === 'dark'

    const bgClass = isDark ? 'bg-transparent' : 'bg-white'
    const borderClass = isDark ? 'border-white' : 'border-gray-200'
    const titleColor = isDark ? 'text-white' : 'text-gray-900'
    const descColor = isDark ? 'text-gray-300' : 'text-gray-600'
    const iconColor = isDark ? 'text-purple-500' : 'text-purple-600'

  return (
    <article
      role="region"
      aria-labelledby={`feature-${title}`}
      className={[
        bgClass,
        'border',
        borderClass,
        'rounded-3xl',
        'p-6',
        'flex items-start space-x-4',
        className,
      ].join(' ')}
    >
      <div className={`${iconColor} flex-shrink-0`}>
        {icon}
      </div>
      <div>
        <h3
          id={`feature-${title}`}
          className={`${titleColor} text-lg font-semibold leading-tight`}
        >
          {title}
        </h3>
        <p className={`mt-2 ${descColor} text-sm leading-relaxed`}>
          {description}
        </p>
      </div>
    </article>
  )
}

export default React.memo(FeatureCard)
