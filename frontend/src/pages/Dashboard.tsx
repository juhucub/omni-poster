import React from 'react';
import Sidebar from '../components/Sidebar';
import Header from '../components/Header';
import Summary from '../components/Summary';

const Dashboard = () => {
  return (
    <div className="flex min-h-screen bg-gradient-to-br from-blue-50 via-purple-100 to-gray-100 text-gray-800">
      <Sidebar />
      <main className="flex-1 p-6 space-y-6">
        <Header />
        <Summary />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          
        </div>
       
      </main>
    </div>
  );
};

export default Dashboard;
