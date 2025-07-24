import React from 'react';
import { Search, Bell } from 'lucide-react';

const Header = () => {
  return (
    <header className="flex flex-col md:flex-row md:items-center justify-between space-y-4 md:space-y-0 border-none border-gray-400 p-4">
      <div>
        <h2 className="text-3xl font-bold text-white">Good Morning 👋</h2>
        <p className="text-sm text-gray-200">Welcome Back, Jacob — Saturday, 7 Dec, 2021</p>
      </div>
      <div className="flex items-center space-x-4">
        <div className="relative">
          <input
            type="text"
            placeholder="Search item"
            className="pl-10 pr-4 py-2 rounded-md bg-white shadow-sm border border-gray-300 focus:outline-1 focus:ring-2 focus:ring-blue-400"
          />
          <Search className="absolute left-3 top-2.5 text-gray-400" />
        </div>
        <button className="relative p-2 rounded-full bg-white shadow-md hover:bg-purple-50">
          <Bell className="text-purple-600" />
          <span className="absolute top-0 right-0 block h-2 w-2 rounded-full bg-red-500 ring-2 ring-white"></span>
        </button>
        <img
          src="url-to-avatar"
          alt="Profile"
          className="w-10 h-10 rounded-full border-2 border-white"
        />
      </div>
    </header>
  );
};

export default Header;
