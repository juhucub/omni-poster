import React from 'react';

const Statistics = () => {
  const stats = {
    title: 'Statistics',
    views: '48k views',
    months: ['Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul'],
    bars: [
      { label: 'Feb', value: 1 },
      { label: 'Mar', value: 2 },
      { label: 'Apr', value: 5 },
      { label: 'May', value: 4 },
      { label: 'Jun', value: 3 },
      { label: 'Jul', value: 4 }
    ],
    income: { label: 'Income', value: '$32,127.87' },
    expenses: { label: 'Expenses', value: '$23,521.87' }
  };

  return (
    <section className="bg-white rounded-lg shadow-md p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xl font-semibold">{stats.title}</h3>
        <span className="text-sm text-gray-500">{stats.views}</span>
      </div>
      <div className="flex items-end space-x-4 h-40 mb-6">
        {stats.bars.map((bar, index) => (
          <div key={index} className="flex flex-col items-center">
            <div
              className="w-6 bg-blue-500 rounded-t"
              style={{ height: `${bar.value * 20}px` }}
            ></div>
            <span className="text-xs mt-2 text-gray-500">{bar.label}</span>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="p-4 bg-green-50 rounded-lg">
          <h4 className="text-sm text-gray-500">{stats.income.label}</h4>
          <p className="text-lg font-bold text-green-600">{stats.income.value}</p>
        </div>
        <div className="p-4 bg-red-50 rounded-lg">
          <h4 className="text-sm text-gray-500">{stats.expenses.label}</h4>
          <p className="text-lg font-bold text-red-600">{stats.expenses.value}</p>
        </div>
      </div>
    </section>
  );
};

export default Statistics;
