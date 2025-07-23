import React, { useRef, useState } from 'react';
import {useTheme} from '../hooks/useTheme.tsx';
import { useInViewFadeIn } from '../hooks/useInViewFadeIn.tsx';
import Hero from '../components/Hero.tsx';
import StatsGrid from '../components/StatsSection.tsx';
import {
    FiHeart,
    FiCheckCircle,
    FiMail,
    FiRefreshCw,
  } from 'react-icons/fi'
  import FeatureCard from '../components/FeatureCard.tsx';
import { useScrollClamp } from '../hooks/useScrollClamp.tsx';

const stats: StatsGrid[] = [
    { value: '3K+', label: 'Videos launched monthly', description: 'Hands-free posting to every channel' },
    { value: '1.2K', label: 'Creators thriving', description: 'Growing audiences with smart tools' },
    { value: '5M+', label: 'Views delivered', description: 'Expanding reach with every upload' },
    { value: '24/7', label: 'Always-on scheduling', description: 'Your content, never off the clock' },
  ]


interface RawFeature {
    icon: React.ReactNode
    title: string
    description: string
    initialAngle: number     // e.g. -3
    maxDelta: number         // e.g. +6  (so final = initial + maxDelta)
  }

  const features: RawFeature[] = [
    {
      icon: <FiHeart size={24} aria-hidden />,
      title: 'Safe accounts, easy scheduling',
      description:
        'Connect your social accounts securely. Schedule posts, track uploads, and keep your content calendar organized—never miss a moment.',
      initialAngle: -3,
      maxDelta: 6,
    },
    {
      icon: <FiCheckCircle size={24} aria-hidden />,
      title: 'One-click uploads, everywhere you post',
      description:
        'Publish to YouTube, TikTok, and Instagram all at once. Our tool adapts to each platform’s quirks, so you don’t have to sweat the details.',
      initialAngle: 1,
      maxDelta: -4,
    },
    {
      icon: <FiMail size={24} aria-hidden />,
      title: 'AI-powered metadata for more reach',
      description:
        'Get smart suggestions for titles, tags, and hashtags that help your content get discovered. Let AI handle the details so you can focus on your message.',
      initialAngle: -2,
      maxDelta: 5,
    },
    {
      icon: <FiRefreshCw size={24} aria-hidden />,
      title: 'Automate content, schedule, and grow',
      description:
        'Take control of your content workflow—create, schedule, and publish across every platform from one place. No more tab-hopping or missed deadlines, just smooth, stress-free posting.',
      initialAngle: 2,
      maxDelta: -6,
    },
  ]
  
  export const FeaturesGrid: React.FC = () => (
    <section className="relative bg-[#0f172a] py-24 overflow-hidden">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 justify-center">
        {features.map((feat) => (
          <RotatingCard key={feat.title} {...feat} />
        ))}
      </div>
    </section>
  )

  /** breaks out one card with dynamic scroll-based rotation */
  function RotatingCard({ icon, title, description, initialAngle, maxDelta }: RawFeature) {
    const ref = useRef<HTMLDivElement>(null)
    // this angle will stay ≥ initialAngle, then interpolate to initialAngle+maxDelta
    const angle = useScrollClamp(ref, initialAngle, maxDelta, 0.8)
  
    return (
      <div
        ref={ref}
        className="w-[360px]" 
        style={{
          transform: `rotate(${angle}deg)`,
          transition: 'transform 0.1s ease-out',
        }}
      >
        <FeatureCard icon={icon} title={title} description={description} />
      </div>
    )
  }


export default function LandingPage() {
  return (
    <>
      <Nav />
      <Hero
        title="AUTOMATE EVERY POST, EVERYWHERE"
        subtitle="Effortlessly create, schedule, and share videos across all your channels. From idea to upload, manage every step in one seamless dashboard—no more juggling platforms or missing your moment."
        primaryActionText="Start now"
        onPrimaryAction={() => console.log('Start now')}
        secondaryActionText="Watch demo"
        onSecondaryAction={() => console.log('Watch demo')}
        imageSrc="/corn.png"
        imageAlt="Video management dashboard"
        stats={stats}
        />

        <FeaturesGrid />
        <Hero
        title="AUTOMATE EVERY POST, EVERYWHERE"
        subtitle="Effortlessly create, schedule, and share videos across all your channels. From idea to upload, manage every step in one seamless dashboard—no more juggling platforms or missing your moment."
        primaryActionText="Start now"
        onPrimaryAction={() => console.log('Start now')}
        secondaryActionText="Watch demo"
        onSecondaryAction={() => console.log('Watch demo')}
        imageSrc="/corn.png"
        imageAlt="Video management dashboard"
        stats={stats}
        />
    </>
  );
}


function Nav() {
  return (
    <nav className="bg-gray-900 text-white fixed w-full z-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
        <a href="#" className="flex items-center space-x-2">
          <Logo className="h-8 w-8 text-white" />
          <span className="text-xl font-bold uppercase">Dataway</span>
        </a>
        <div className="hidden md:flex space-x-8">
          <Dropdown title="Features">
            <a href="#">Video creator</a>
            <a href="#">Smart metadata</a>
            <a href="#">Unified uploader</a>
          </Dropdown>
          <a href="#" className="hover:text-gray-300">How it works</a>
          <a href="#" className="hover:text-gray-300">Insights</a>
          <Dropdown title="Help">
            <a href="#">Support</a>
            <a href="#">Contact</a>
          </Dropdown>
        </div>
        <div className="hidden md:flex">
          <a href="#" className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded">Try free</a>
        </div>
        <MobileMenu />
      </div>
    </nav>
  );
}


function FeatureCards() {
  const features = [
    { title: 'Automate content, schedule, and grow', icon: ContentIcon },
    { title: 'Create stunning videos in minutes', icon: VideoIcon },
    { title: 'AI-powered metadata for more reach', icon: MetaIcon },
    { title: 'One-click uploads, everywhere you post', icon: UploadIcon },
  ];
  return (
    <section className="py-16 bg-gray-900 text-white overflow-hidden">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {features.map((f, idx) => (
            <div
              key={f.title}
              className={`p-6 bg-gray-800 border border-gray-700 rounded-lg transform ${idx % 2 === 0 ? '-rotate-3' : 'rotate-3'} hover:rotate-0 transition`}
            >
              <div className="w-12 h-12 mb-4"><f.icon /></div>
              <h3 className="text-lg font-semibold uppercase mb-2">{f.title}</h3>
              <p className="text-sm text-gray-400">{f.title} description goes here.</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function InfoCards() {
  const infos = [
    { title: 'Safe accounts, easy scheduling', icon: ShieldIcon },
    { title: 'Cloud storage, instant access', icon: CloudIcon },
  ];
  return (
    <section className="py-16 bg-white text-gray-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 md:grid-cols-2 gap-8">
        {infos.map((inf) => (
          <div key={inf.title} className="p-6 bg-gray-50 rounded-lg shadow space-y-4">
            <div className="w-12 h-12 text-purple-600"><inf.icon /></div>
            <h3 className="text-xl font-semibold">{inf.title}</h3>
            <p className="text-sm text-gray-600">{inf.title} detailed text goes here.</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function CallToAction() {
  return (
    <section className="py-16 bg-gray-900 text-white text-center">
      <div className="max-w-3xl mx-auto space-y-6">
        <h2 className="text-3xl font-bold">Start creating and scheduling today</h2>
        <p className="text-lg text-gray-400">Streamline your entire social workflow with powerful automation and intuitive tools.</p>
        <a href="#" className="px-8 py-4 bg-purple-600 hover:bg-purple-700 text-white rounded-lg">Try free</a>
      </div>
    </section>
  );
}

function FAQ() {
  const faqs = [
    { q: 'How do I post everywhere at once?', a: 'Just pick your platforms, set your schedule, and your videos go live across YouTube, TikTok, and Instagram—no extra steps or logins needed.' },
    { q: 'Which video files can I upload?', a: 'Most popular video and audio formats are supported. We optimize automatically.' },
    { q: 'Can I switch between different accounts?', a: 'Yes! Manage multiple brands from one dashboard.' },
    { q: 'How is my data kept safe?', a: 'Your data is encrypted end-to-end and stored securely.' },
  ];
  return (
    <section className="py-16 bg-gray-50 text-gray-900">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        <div className="text-center space-y-4">
          <h2 className="text-2xl font-bold">Your top questions, explained simply</h2>
          <p className="text-gray-600">No jargon, just quick answers so you can get started fast.</p>
        </div>
        <div className="space-y-6">
          {faqs.map((f) => (
            <div key={f.q} className="border rounded-lg p-4 bg-white shadow">
              <h4 className="text-lg font-medium">{f.q}</h4>
              <p className="mt-2 text-gray-700">{f.a}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Contact() {
  const contacts = [
    { title: 'Email our team', link: 'mailto:email@website.com', linkText: 'email@website.com', icon: MailIcon },
    { title: 'Give us a call', link: 'tel:+15550000000', linkText: '+1 (555) 000-0000', icon: PhoneIcon },
  ];
  return (
    <section className="py-16 bg-gray-800 text-white">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 md:grid-cols-2 gap-8">
        {contacts.map((c) => (
          <div key={c.title} className="p-6 bg-gray-700 rounded-lg space-y-4">
            <div className="w-12 h-12 text-purple-400"><c.icon /></div>
            <h5 className="text-xl font-semibold">{c.title}</h5>
            <a href={c.link} className="underline">{c.linkText}</a>
          </div>
        ))}
      </div>
    </section>
  );
}

function Footer() {
  const cols = [
    { heading: 'Platform', links: ['Home', 'Upload', 'Schedule', 'Track', 'Help'] },
    { heading: 'Features', links: ['Video', 'Tags', 'Accounts', 'Queue', 'Files'] },
    { heading: 'Resources', links: ['Docs', 'API', 'Guides', 'Blog', 'Status'] },
    { heading: 'Company', links: ['About', 'Team', 'Careers', 'Contact', 'Legal'] },
  ];
  const social = ['Facebook', 'Instagram', 'X', 'LinkedIn', 'YouTube'];
  return (
    <footer className="bg-gray-900 text-gray-500 py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
        {cols.map((col) => (
          <div key={col.heading} className="space-y-4">
            <h6 className="font-semibold uppercase text-gray-400">{col.heading}</h6>
            <ul className="space-y-2">
              {col.links.map((l) => (
                <li key={l}><a href="#" className="hover:text-white">{l}</a></li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row justify-between items-center">
        <div className="text-gray-600">All rights reserved © 2025 Omniposter</div>
        <div className="flex space-x-4 mt-4 md:mt-0">
          {social.map((s) => <a key={s} href="#" className="hover:text-white text-gray-400">{s}</a>)}
        </div>
      </div>
    </footer>
  );
}

// Utility Components and Icons
function Dropdown({ title, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center space-x-1 text-white hover:text-gray-300"
      >
        <span>{title}</span>
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="absolute mt-2 bg-gray-800 text-white rounded-lg shadow-lg p-4 space-y-2">
          {children}
        </div>
      )}
    </div>
  );
}

function MobileMenu() {
  return (
    <button className="md:hidden text-white">
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
      </svg>
    </button>
  );
}

function Logo(props) {
  return (
    <svg {...props} viewBox="0 0 33 33" fill="currentColor">
      <path d="M28,0H5C2.24,0,0,2.24,0,5v23c0,2.76,2.24,5,5,5h23c2.76,0,5-2.24,5-5V5c0-2.76-2.24-5-5-5Z" />
    </svg>
  );
}

// Icon Placeholders
const ContentIcon = () => (
  <svg className="w-full h-full text-purple-400" fill="currentColor" viewBox="0 0 24 24">
    <rect x="4" y="4" width="16" height="16" rx="2" />
  </svg>
);

const VideoIcon = () => (
  <svg className="w-full h-full text-purple-400" fill="currentColor" viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="10" />
  </svg>
);

const MetaIcon = () => (
  <svg className="w-full h-full text-purple-400" fill="currentColor" viewBox="0 0 24 24">
    <path d="M12 2l10 20H2L12 2z" />
  </svg>
);

const UploadIcon = () => (
  <svg className="w-full h-full text-purple-400" fill="currentColor" viewBox="0 0 24 24">
    <path d="M4 12l8-8 8 8M12 4v16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const ShieldIcon = () => (
  <svg className="w-full h-full text-purple-400" fill="currentColor" viewBox="0 0 24 24">
    <path d="M12 2l8 4v6c0 5-3 9-8 10-5-1-8-5-8-10V6l8-4z" />
  </svg>
);

const CloudIcon = () => (
  <svg className="w-full h-full text-purple-400" fill="currentColor" viewBox="0 0 24 24">
    <ellipse cx="12" cy="12" rx="8" ry="5" />
  </svg>
);

const MailIcon = () => (
  <svg className="w-full h-full text-purple-400" fill="currentColor" viewBox="0 0 24 24">
    <path d="M4 4h16v16H4V4z" stroke="currentColor" strokeWidth="2" fill="none" />
    <path d="M4 4l8 8 8-8" stroke="currentColor" strokeWidth="2" />
  </svg>
);

const PhoneIcon = () => (
  <svg className="w-full h-full text-purple-400" fill="currentColor" viewBox="0 0 24 24">
    <path d="M6 2h12v4l-4 4 4 4v4H6v-4l4-4-4-4V2z" />
  </svg>
);
