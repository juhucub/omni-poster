import React from 'react'

export interface Stat {
  /** e.g. "3K+" */
  value: string
  /** e.g. "Videos launched monthly" */
  label: string
  /** e.g. "Hands-free posting to every channel" */
  description: string
}

export interface HeroSectionProps {
  title: string
  subtitle: string
  primaryActionText: string
  onPrimaryAction: () => void
  secondaryActionText: string
  onSecondaryAction: () => void
  imageSrc: string
  imageAlt?: string
  stats: Stat[]
}

const HeroSection: React.FC<HeroSectionProps> = ({
  title,
  subtitle,
  primaryActionText,
  onPrimaryAction,
  secondaryActionText,
  onSecondaryAction,
  imageSrc,
  imageAlt = '',
  stats,
}) => (
  <section className="bg-blue-600">
    {/* Top: headline, copy, buttons, image */}
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 flex items-center justify-between">
      <div className="lg:w-1/2">
        <h1 className="text-white uppercase font-extrabold tracking-tight text-4xl sm:text-5xl lg:text-6xl leading-tight">
          {title}
        </h1>
        <p className="mt-4 max-w-prose text-lg text-gray-300">
          {subtitle}
        </p>
        <div className="mt-8 flex space-x-4">
          <button
            onClick={onPrimaryAction}
            aria-label={primaryActionText}
            className="inline-flex items-center justify-center px-8 py-3 border border-transparent text-base font-medium rounded-md text-white bg-[#7b5cff] hover:bg-[#694ce3] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#7b5cff]"
          >
            {primaryActionText}
          </button>
          <button
            onClick={onSecondaryAction}
            aria-label={secondaryActionText}
            className="inline-flex items-center justify-center px-8 py-3 border border-white text-base font-medium rounded-md text-white bg-transparent hover:bg-white hover:text-[#0b0f1a] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-white"
          >
            {secondaryActionText}
          </button>
        </div>
      </div>

      <div className="mt-10 lg:mt-0 lg:w-1/2 lg:flex lg:justify-end">
        <img
          src={imageSrc}
          alt={imageAlt}
          className="w-full max-w-lg rounded-xl shadow-xl"
        />
      </div>
    </div>

    {/* Bottom: stats row */}
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-20">
      <dl className="flex flex-cols-2 md:flex-cols-4 gap-x-4 gap-y-6">
        {stats.map(({ value, label, description }) => (
          <div key={label} className="text-center">
            <dt className="text-3xl font-extrabold text-white">{value}</dt>
            <dd className="mt-2 text-lg font-medium text-white">{label}</dd>
            <dd className="mt-1 text-sm text-gray-400">{description}</dd>
          </div>
        ))}
      </dl>
    </div>
  </section>
)

export default React.memo(HeroSection)
