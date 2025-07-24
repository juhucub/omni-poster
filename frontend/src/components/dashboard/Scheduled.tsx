import React from 'react';

const Scheduled = () => {
  const scheduled = [
    {
      name: 'Thriller Stories for the campfire',
      avatar: 'TA',
      datetime: '12 March 25 @ 7:30 pm',
      views: '514'
    },
    {
      name: 'Esther Howard',
      avatar: 'BR',
      datetime: '12 March 30 @ 7:30 pm',
      amount: '-$948.55'
    },
    {
      name: 'Guy Hawkins',
      avatar: 'BR',
      datetime: '12 March 21 @ 7:30 pm',
      amount: '-$948.55'
    }
  ];

  return (
    <section className="bg-white rounded-lg shadow-md p-6">
      <h3 className="text-xl font-semibold mb-4">Scheduled</h3>
      <ul className="space-y-4">
        {scheduled.map((entry, idx) => (
          <li key={idx} className="flex items-center space-x-4">
            <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center font-bold text-blue-600 border">
              {entry.avatar}
            </div>
            <div className="flex-1">
              <h4 className="font-semibold text-gray-800">{entry.name}</h4>
              <p className="text-sm text-gray-500">{entry.datetime}</p>
            </div>
            <div className="text-right">
              {entry.views && (
                <p className="text-lg font-bold text-green-600">{entry.views} views</p>
              )}
              {entry.amount && (
                <p className="text-lg font-bold text-red-500">{entry.amount}</p>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
};

export default Scheduled;
