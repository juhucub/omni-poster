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
}

const FeatureCard: React.FC<FeatureCardProps> = ({
  icon,
  title,
  description,
  className = '',
}) => {
  const titleId = `feature-card-title-${title
    .toLowerCase()
    .replace(/\s+/g, '-')}`

  return (
    <article
      role="region"
      aria-labelledby={titleId}
      className={
        [
          // transparent bg so the dark section shows through
          'bg-transparent',
          // 1px white border, softly rounded corners
          'border border-white rounded-2xl',
          // comfortable inner padding
          'p-6',
          // horizontal layout: icon + text
          'flex items-start space-x-4',
          // allow parent to override width or rotation
          className,
        ].join(' ')
      }
    >
      <div className="flex-shrink-0 text-purple-500">
        {icon}
      </div>
      <div>
        <h3
          id={titleId}
          className="text-white text-lg font-semibold leading-tight"
        >
          {title}
        </h3>
        <p className="mt-2 text-gray-300 text-sm leading-relaxed">
          {description}
        </p>
      </div>
    </article>
  )
}

export default React.memo(FeatureCard)
