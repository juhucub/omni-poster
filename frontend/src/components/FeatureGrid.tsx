import React, { useRef } from 'react'
import FeatureCard, { FeatureCardProps } from './FeatureCard.tsx'
import { useScrollClamp } from '../hooks/useScrollClamp.tsx'
import {
  FiHeart,
  FiCheckCircle,
  FiMail,
  FiRefreshCw,
  FiStar,
  FiZap,
  FiSmile,
  FiClock,
} from 'react-icons/fi'

interface features {
    icon: React.ReactNode
    title: string
    description: string
    initialAngle: number     // e.g. -3
    maxDelta: number         // e.g. +6  (so final = initial + maxDelta)
  }


const features: features[] = [
{
    //4 Animated dark cards
    icon: <FiHeart size={24} aria-hidden />,
    title: 'Safe accounts, easy scheduling',
    description:
    'Connect your social accounts securely. Schedule posts, track uploads, and keep your content calendar organized—never miss a moment.',
    variant: 'dark',   
    initialAngle: -3,
    maxDelta: 6,
},
{
    icon: <FiCheckCircle size={24} aria-hidden />,
    title: 'One-click uploads, everywhere you post',
    description:
    'Publish to YouTube, TikTok, and Instagram all at once. Our tool adapts to each platform’s quirks, so you don’t have to sweat the details.',
    variant: 'dark', 
    initialAngle: 1,
    maxDelta: -4,
},
{
    icon: <FiMail size={24} aria-hidden />,
    title: 'AI-powered metadata for more reach',
    description:
    'Get smart suggestions for titles, tags, and hashtags that help your content get discovered. Let AI handle the details so you can focus on your message.',
    variant: 'dark', 
    initialAngle: -2,
    maxDelta: 5,
},
{
    icon: <FiRefreshCw size={24} aria-hidden />,
    title: 'Automate content, schedule, and grow',
    description:
    'Take control of your content workflow—create, schedule, and publish across every platform from one place. No more tab-hopping or missed deadlines, just smooth, stress-free posting.',
    variant: 'dark', 
    initialAngle: 2,
    maxDelta: -6,
},
// next four → static light cards
{
    icon: <FiStar size={24} aria-hidden />,
    title: 'Always-on analytics',
    description: '…',
    variant: 'light', 
    initialAngle: 0,
    maxDelta: 0,
},
{
    icon: <FiZap size={24} aria-hidden />,
    title: 'Instant transcoding',
    description: '…',
    variant: 'light', 
    initialAngle: 0,
    maxDelta: 0,
},
{
    icon: <FiSmile size={24} aria-hidden />,
    title: 'Friendly UI',
    description: '…',
    variant: 'light', 
    initialAngle: 0,
    maxDelta: 0,
},
{
    icon: <FiClock size={24} aria-hidden />,
    title: '24/7 support',
    description: '…',
    variant: 'light', 
    initialAngle: 0,
    maxDelta: 0,
},
]


export const FeaturesGrid: React.FC = () => (
    <section className="relative bg-[#0f172a] py-24 overflow-hidden">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-12 lg:gap-16 justify-center">
        {features.map((feat, idx) => (
          <RotatingCard 
            key={feat.title} 
            {...feat} 
            animate={idx < 4}
            />
        ))}
      </div>
    </section>
  )

    type RotatingCardProps = features & { animate: boolean }

   /** breaks out one card with dynamic scroll-based rotation */
   function RotatingCard({ icon, title, description, variant, initialAngle, maxDelta, animate }: RotatingCardProps) {
    const ref = useRef<HTMLDivElement>(null)
    // this angle will stay ≥ initialAngle, then interpolate to initialAngle+maxDelta
    const angle = animate
    ? useScrollClamp(ref, initialAngle, maxDelta, 0.8)
    : initialAngle  // static cards stay unrotated
  
    return (
      <div
        ref={ref}
        className="w-[360px]" 
        style={{
          transform: `rotate(${angle}deg)`,
          transition: animate ? 'transform 0.1s ease-out' : 'none',
        }}
      >
        <FeatureCard 
            icon={icon} 
            title={title} 
            description={description}
            variant={variant} />
      </div>
    )
  }

