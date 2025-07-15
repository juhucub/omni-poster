import React from 'react';
import { FaSearch, FaBell } from 'react-icons/fa';

const Header = () => {
  return (
    <header className="flex flex-col md:flex-row md:items-center justify-between space-y-4 md:space-y-0">
      <div>
        <h2 className="text-3xl font-bold text-gray-800">Good Morning 👋</h2>
        <p className="text-sm text-gray-500">Welcome Back, Jacob — Saturday, 7 Dec, 2021</p>
      </div>
      <div className="flex items-center space-x-4">
        <div className="relative">
          <input
            type="text"
            placeholder="Search item"
            className="pl-10 pr-4 py-2 rounded-md bg-white shadow-sm border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <FaSearch className="absolute left-3 top-2.5 text-gray-400" />
        </div>
        <button className="relative p-2 rounded-full bg-white shadow-md hover:bg-blue-50">
          <FaBell className="text-blue-600" />
          <span className="absolute top-0 right-0 block h-2 w-2 rounded-full bg-red-500 ring-2 ring-white"></span>
        </button>
        <img
          src="url-to-avatar"
          alt="Profile"
          className="w-10 h-10 rounded-full border-2 border-blue-600"
        />
      </div>
    </header>
  );
};

export default Header;
