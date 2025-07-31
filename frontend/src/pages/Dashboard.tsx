import React from 'react';
import Sidebar from '../components/Sidebar.tsx';
import Header from '../components/dashboard/Header';
import Summary from '../components/dashboard/Summary.jsx';
import Promo from '../components/dashboard/Promo';
import Metrics from '../components/dashboard/Metrix';
import Statistics from '../components/dashboard/Statistics';

const Dashboard = () => {
  return (
    <div className="flex min-h-screen bg-gradient-to-br from-[#17183D] via-[#2C275C] to-[#10123B] text-gray-800">
      <Sidebar />
      <main className="flex-1 p-6 space-y-6">
        <Header />
        <Summary />
        <Metrics />
        <Statistics />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
         { /* <Uploads />
          <Scheduled /> */ }
        </div>
        <Promo />
      </main>
    </div>
  );
};

export default Dashboard;
