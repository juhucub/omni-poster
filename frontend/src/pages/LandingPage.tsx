import React from 'react';
import Navigation from '../components/landing-page/Navigation.tsx';
import Hero from '../components/landing-page/Hero.tsx';
import FeaturesGrid from '../components/landing-page/FeaturesGrid.tsx';
import MainFeatures from '../components/landing-page/MainFeatures.tsx';
import CTASection from '../components/landing-page/CTASection.tsx';
import FAQSection from '../components/landing-page/FAQSection.tsx';
import ContactSection from '../components/landing-page/ContactSection.tsx';
import Footer from '../components/landing-page/Footer.tsx';





export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#10123B]">
      <Navigation />
      <Hero />
      <FeaturesGrid />
      <MainFeatures />
      <CTASection />
      <FAQSection />
      <ContactSection />
      <Footer />
    </div>
  );
};





