import React from 'react';
import { Play } from 'lucide-react';

interface StatCard {
  number: string;
  title: string;
  description: string;
}

const Hero: React.FC = () => {
  const stats: StatCard[] = [
    { number: "3K+", title: "Videos launched monthly", description: "Hands-free posting to every channel" },
    { number: "1.2K", title: "Creators thriving", description: "Growing audiences with smart tools" },
    { number: "5M+", title: "Views delivered", description: "Expanding reach with every upload" },
    { number: "24/7", title: "Always-on scheduling", description: "Your content, never off the clock" }
  ];

  return (
    <section className="bg-gradient-to-br from-[#17183D] to-[#10123B] py-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid lg:grid-cols-5 gap-12 items-center">
          {/* Hero Content - Takes up 2 columns */}
          <div className="lg:col-span-2">
            <h1 className="text-4xl lg:text-5xl font-bold text-white mb-6">
              AUTOMATE EVERY POST, EVERYWHERE
            </h1>
            <p className="text-lg text-gray-100 mb-8">
              Effortlessly create, schedule, and share videos across all your channels. From idea to upload, manage every step in one seamless dashboard—no more juggling platforms or missing your moment.
            </p>
            <div className="flex flex-col sm:flex-row gap-4">
              <button className="bg-purple-600 text-white px-8 py-3 rounded-lg hover:bg-purple-700 transition-colors font-medium">
                Start now
              </button>
              <button className="border border-gray-300 text-white px-8 py-3 rounded-lg hover:border-purple-700 transition-colors font-medium flex items-center justify-center space-x-2">
                <Play className="w-5 h-5" />
                <span>Watch demo</span>
              </button>
            </div>
          </div>

          {/* Hero Image - Takes up 3 columns */}
          <div className="lg:col-span-3 relative">
            <div className="bg-gradient-to-r from-purple-600 to-purple-950 rounded-2xl aspect-video flex items-center justify-center text-white shadow-2xl">
              <div className="text-center">
                <div className="w-32 h-32 bg-white/20 rounded-full flex items-center justify-center mx-auto mb-6 hover:bg-white/30 transition-colors cursor-pointer">
                  <Play className="w-16 h-16" />
                </div>
                <h3 className="text-2xl font-bold mb-2">Content Automation Demo</h3>
                <p className="text-lg opacity-90">See it in action</p>
              </div>
            </div>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-8 mt-16">
          {stats.map((stat, index) => (
            <div key={index} className="text-center">
              <h3 className="text-3xl font-bold text-white mb-2">{stat.number}</h3>
              <p className="font-medium text-gray-100 mb-1">{stat.title}</p>
              <p className="text-sm text-gray-400">{stat.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Hero;