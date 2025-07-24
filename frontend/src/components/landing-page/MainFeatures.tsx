import React from 'react';

const MainFeatures: React.FC = () => {
    const mainFeatures = [
      {
        icon: (
          <svg className="w-16 h-16 text-purple-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M12.5 18.25C16.2279 18.25 19.25 15.2279 19.25 11.5C19.25 7.77208 16.2279 4.75 12.5 4.75C8.77208 4.75 5.75 7.77208 5.75 11.5C5.75 12.6007 6.01345 13.6398 6.48072 14.5578L5 19L9.71819 17.6519C10.5664 18.0361 11.5082 18.25 12.5 18.25Z"/>
          </svg>
        ),
        title: "One dashboard, every platform, zero hassle",
        description: "Sync your accounts, set your schedule, and let your videos post themselves. Skip the manual uploads—enjoy seamless sharing to YouTube, TikTok, and Instagram, all in one place."
      },
      {
        icon: (
          <svg className="w-16 h-16 text-purple-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M9.24998 18.7103C6.60958 17.6271 4.75 15.0307 4.75 12C4.75 8.96938 6.60958 6.37304 9.24997 5.28979"/>
            <path d="M14.75 5.28979C17.3904 6.37303 19.25 8.96938 19.25 12.0001C19.25 15.0307 17.3904 17.6271 14.75 18.7103"/>
            <path d="M4 19.2501L8.99998 19.2501C9.13805 19.2501 9.24998 19.1381 9.24998 19.0001L9.24997 14"/>
            <path d="M20 4.75L15 4.75003C14.8619 4.75003 14.75 4.86196 14.75 5.00003L14.75 10.0001"/>
          </svg>
        ),
        title: "Create videos in just minutes",
        description: "Mix audio, video, and metadata with a few clicks. Our intuitive tools help you craft platform-ready content, so you can focus on your ideas—not the technical details."
      },
      {
        icon: (
          <svg className="w-16 h-16 text-purple-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="12" cy="9" r="3"/>
            <path d="M17.5 17.25V16.5C17.5 14.8431 16.1569 13.5 14.5 13.5H9.5C7.84315 13.5 6.5 14.8431 6.5 16.5V17.25"/>
          </svg>
        ),
        title: "AI-powered metadata, made simple",
        description: "Generate standout titles, tags, and thumbnails with smart suggestions. Keep your content organized, searchable, and ready to reach more viewers."
      },
      {
        icon: (
          <svg className="w-16 h-16 text-purple-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M11 6.75H5.75V18.25H17.25V13"/>
            <path d="M13.5 4.75H19.25V10.5"/>
            <path d="M19.25 4.75L11.5 12.5"/>
          </svg>
        ),
        title: "Plan, schedule, and track with ease",
        description: "Set your posts, monitor progress, and get instant updates. Stay organized with automated scheduling and detailed logs—never miss a beat."
      }
    ];
  
    return (
      <section className="bg-white text-black py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {mainFeatures.map((feature, index) => (
              <div key={index} className="bg-white rounded-xl p-8 border-3 border-black">
                <div className="text-blue-400 mb-6">
                  {feature.icon}
                </div>
                <h3 className="text-2xl font-bold mb-4">
                  {feature.title}
                </h3>
                <p className="text-black">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>
    );
  };

  export default MainFeatures;