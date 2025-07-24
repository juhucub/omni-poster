import React from 'react';

const CTASection: React.FC = () => {
    return (
      <section className="bg-[#10123B] py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="bg-gradient-to-r from-[#17183D] to-[#10123B] rounded-2xl p-12 text-center text-white border-2 border-gray-700">
            <h2 className="text-4xl font-bold mb-6">
              AUTOMATE EVERY POST, EVERYWHERE
            </h2>
            <p className="text-xl mb-8 max-w-3xl mx-auto">
              Effortlessly create, schedule, and share videos across all your favorite platforms. Take control of your content—no limits, no stress. Join a community of creators making social media simple.
            </p>
            <button className="bg-purple-600 text-white px-8 py-3 rounded-lg hover:bg-gray-100 transition-colors font-medium">
              Try free
            </button>
          </div>
        </div>
      </section>
    );
  };

  export default CTASection;