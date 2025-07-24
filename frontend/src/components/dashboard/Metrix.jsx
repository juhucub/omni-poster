import React from 'react';

const Metrics = () => {
  const accounts = [
    { label: 'Account Name 1', views: '21,345,132' },
    { label: 'Account Name 2', views: '2,134,532' },
    { label: 'Account Name 3', views: '21,345' }
  ];

  return (
    <section className="bg-white rounded-lg shadow-md p-6">
      <h3 className="text-xl font-semibold mb-4">Account Metrics</h3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
        {accounts.map((account, idx) => (
          <div
            key={idx}
            className="bg-blue-50 p-4 rounded-lg text-center shadow-sm hover:shadow-md transition"
          >
            <h4 className="text-lg font-medium text-gray-800 mb-2">{account.label}</h4>
            <p className="text-2xl font-bold text-blue-600">{account.views}</p>
          </div>
        ))}
      </div>
    </section>
  );
};

export default Metrics;