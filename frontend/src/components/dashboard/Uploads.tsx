import React from 'react';

const Uploads = () => {
  const uploads = [
    {
      name: 'Horror Stories to tell in the dark',
      avatar: 'url-to-avatar-1',
      accountType: 'YouTube',
      date: '23 March 25',
      type: 'Horror',
      views: '4,855'
    },
    {
      name: 'Horror Stories to tell in the light',
      avatar: 'url-to-avatar-1',
      accountType: 'TikTok',
      date: '23 March 25',
      type: 'Horror',
      views: '12'
    },
    {
      name: 'Reddit Stories',
      avatar: 'url-to-avatar-2',
      accountType: 'Instagram',
      date: '28 March 25',
      type: 'Engagement',
      views: '94,855'
    },
    {
      name: 'Esther Howard',
      avatar: 'url-to-avatar-3',
      accountType: 'YouTube',
      date: '24 March 29',
      type: 'Folklore',
      views: '948'
    }
  ];

  return (
    <section className="bg-white rounded-lg shadow-md p-6">
      <h3 className="text-xl font-semibold mb-4">Latest Uploads</h3>
      <ul className="space-y-4">
        {uploads.map((upload, idx) => (
          <li key={idx} className="flex items-center space-x-4">
            <img
              src={upload.avatar}
              alt={upload.name}
              className="w-12 h-12 rounded-full border"
            />
            <div className="flex-1">
              <h4 className="font-semibold text-gray-800">{upload.name}</h4>
              <p className="text-sm text-gray-500">{upload.accountType} • {upload.type}</p>
              <p className="text-xs text-gray-400">{upload.date}</p>
            </div>
            <div className="text-right">
              <p className="text-lg font-bold text-blue-600">{upload.views}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
};

export default Uploads;
