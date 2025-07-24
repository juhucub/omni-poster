import React from 'react';
import Navigation from '../components/Navigation.tsx';
import Hero from '../components/Hero.tsx';
import FeaturesGrid from '../components/FeaturesGrid.tsx';
import MainFeatures from '../components/MainFeatures.tsx';
import CTASection from '../components/CTASection.tsx';
import FAQSection from '../components/FAQSection.tsx';
import ContactSection from '../components/ContactSection.tsx';
import Footer from '../components/Footer.tsx';





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





