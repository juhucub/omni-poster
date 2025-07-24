import React from 'react';
import { Mail } from 'lucide-react';

interface FeatureCard {
    icon: React.ReactNode;
    title: string;
    description: string;
  }

const FeaturesGrid: React.FC = () => {
    const features: FeatureCard[] = [
      {
        icon: (
          <svg className="w-12 h-12" viewBox="0 0 24 24" fill="none">
            <path d="M9.24998 18.7103C6.60958 17.6271 4.75 15.0307 4.75 12C4.75 8.96938 6.60958 6.37304 9.24997 5.28979" stroke="currentColor" strokeWidth="1.5"/>
            <path d="M14.75 5.28979C17.3904 6.37303 19.25 8.96938 19.25 12.0001C19.25 15.0307 17.3904 17.6271 14.75 18.7103" stroke="currentColor" strokeWidth="1.5"/>
          </svg>
        ),
        title: "Automate content, schedule, and grow",
        description: "Take control of your content workflow—create, schedule, and publish across every platform from one place. No more tab-hopping or missed deadlines, just smooth, stress-free posting."
      },
      {
        icon: (
          <svg className="w-12 h-12" viewBox="0 0 24 24" fill="none">
            <path d="M12.5 18.25C16.2279 18.25 19.25 15.2279 19.25 11.5C19.25 7.77208 16.2279 4.75 12.5 4.75C8.77208 4.75 5.75 7.77208 5.75 11.5C5.75 12.6007 6.01345 13.6398 6.48072 14.5578L5 19L9.71819 17.6519C10.5664 18.0361 11.5082 18.25 12.5 18.25Z" stroke="currentColor" strokeWidth="1.5"/>
          </svg>
        ),
        title: "Create stunning videos in minutes",
        description: "Mix audio, visuals, and metadata effortlessly. Produce scroll-stopping videos ready for any platform, with no tech headaches or complicated steps."
      },
      {
        icon: <Mail className="w-12 h-12" />,
        title: "AI-powered metadata for more reach",
        description: "Get smart suggestions for titles, tags, and hashtags that help your content get discovered. Let AI handle the details so you can focus on your message."
      },
      {
        icon: (
          <svg className="w-12 h-12" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="7.25" stroke="currentColor" strokeWidth="1.5"/>
            <path d="M9 12L11 14L15.5 9.5" stroke="currentColor" strokeWidth="1.5"/>
          </svg>
        ),
        title: "One-click uploads, everywhere you post",
        description: "Publish to YouTube, TikTok, and Instagram all at once. Our tool adapts to each platform's quirks, so you don't have to sweat the details."
      },
      {
        icon: (
          <svg className="w-12 h-12" viewBox="0 0 24 24" fill="none">
            <path d="M17.3654 5.32894C17.8831 5.54543 18.3534 5.86273 18.7495 6.26274L12.0001 19L5.2496 12.3535C4.44951 11.5457 4 10.4501 4 9.3076C4 8.16516 4.44951 7.0695 5.2496 6.26166C6.04975 5.45384 7.13498 5 8.26647 5C9.39804 5 10.4833 5.45384 11.2833 6.26166L12.016 6.99843L12.7158 6.26274C13.112 5.86273 13.5823 5.54543 14.0999 5.32894Z" stroke="currentColor" strokeWidth="1.5"/>
          </svg>
        ),
        title: "Safe accounts, easy scheduling",
        description: "Connect your social accounts securely. Schedule posts, track uploads, and keep your content calendar organized—never miss a moment."
      },
      {
        icon: (
          <svg className="w-12 h-12" viewBox="0 0 24 24" fill="none">
            <path d="M4 12C8.41828 12 12 8.41828 12 4C12 8.41828 15.5817 12 20 12C15.5817 12 12 15.5817 12 20C12 15.5817 8.41828 12 4 12Z" stroke="currentColor" strokeWidth="1.5"/>
          </svg>
        ),
        title: "Cloud storage, instant access",
        description: "Store your videos, assets, and logs safely in the cloud. Access everything you need, whenever inspiration strikes."
      }
    ];
  
    return (
      <section className="bg-[#17183D] py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {features.map((feature, index) => (
              <div 
                key={index} 
                className="bg-[#17183D] rounded-xl p-8 border-2 border-white border-opacity-80 shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="text-purple-600 mb-6">
                  {feature.icon}
                </div>
                <h3 className="text-xl font-bold text-white mb-4 uppercase tracking-wide">
                  {feature.title}
                </h3>
                <p className="text-gray-400">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>
    );
  };

  export default FeaturesGrid;