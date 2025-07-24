import React from 'react';
import Sidebar from '../components/dashboard/Sidebar';
import Header from '../components/dashboard/Header';
import Summary from '../components/account-manager/Summary';
import Promo from '../components/dashboard/Promo';
import Metrics from '../components/dashboard/Metrix';
import Statistics from '../components/dashboard/Statistics';

const Dashboard = () => {
  return (
    <div className="flex min-h-screen bg-gradient-to-br from-blue-50 via-purple-100 to-gray-100 text-gray-800">
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
