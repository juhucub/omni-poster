import React, { JSX, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { Menu, X, ChevronDown } from 'lucide-react';

const Navigation: React.FC = () => {
    const [isMenuOpen, setIsMenuOpen] = useState(false);
    const [isDropdownOpen, setIsDropdownOpen] = useState(false);
    const navigate = useNavigate();
  
    return (
      <nav className="bg-[#17183D] border-1 border-gray-100 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            {/* Logo */}
            <div className="flex items-center space-x-3">
              <span className="text-xl font-bold text-white">Omniposter</span>
            </div>
  
            {/* Desktop Navigation */}
            <div className="hidden md:flex items-center space-x-8">
              <div className="relative">
                <button 
                  onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                  className="flex items-center space-x-1 text-white hover:text-gray-300"
                >
                  <span>Features</span>
                  <ChevronDown className="w-4 h-4" />
                </button>
                
                {isDropdownOpen && (
                  <div className="absolute top-full left-0 mt-2 w-96 bg-white rounded-lg shadow-xl border border-gray-100 p-6">
                    <div className="grid grid-cols-2 gap-6">
                      <div>
                        <h4 className="text-sm font-semibold text-gray-500 uppercase mb-3">Content automation</h4>
                        <div className="space-y-3">
                          <a href="#" className="block p-2 rounded-lg hover:bg-gray-50">
                            <div className="font-medium">Video creator</div>
                            <div className="text-sm text-gray-600">Turn assets into videos instantly.</div>
                          </a>
                          <a href="#" className="block p-2 rounded-lg hover:bg-gray-50">
                            <div className="font-medium">Smart metadata</div>
                            <div className="text-sm text-gray-600">AI titles, tags, and thumbnails.</div>
                          </a>
                        </div>
                      </div>
                      <div>
                        <h4 className="text-sm font-semibold text-gray-500 uppercase mb-3">Scheduling</h4>
                        <div className="space-y-3">
                          <a href="#" className="block p-2 rounded-lg hover:bg-gray-50">
                            <div className="font-medium">Auto scheduler</div>
                            <div className="text-sm text-gray-600">Effortless post planning.</div>
                          </a>
                          <a href="#" className="block p-2 rounded-lg hover:bg-gray-50">
                            <div className="font-medium">Queue manager</div>
                            <div className="text-sm text-gray-600">Edit and reorder with ease.</div>
                          </a>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
              <a href="#" className="text-white hover:text-gray-300">How it works</a>
              <a href="#" className="text-white hover:text-gray-300">Insights</a>
              <a href="#" className="text-white hover:text-gray-300">Help</a>
            </div>
  
            {/* CTA Button */}
            <button 
              onClick={() => navigate('/login')}
              className="hidden md:block bg-purple-600 text-white px-6 py-2 rounded-lg hover:bg-purple-700 transition-colors">
              Try free
            </button>

            {/* Mobile menu button */}
            <button 
              onClick={() => setIsMenuOpen(!isMenuOpen)}
              className="md:hidden p-2"
            >
              {isMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
          </div>
  
          {/* Mobile Navigation */}
          {isMenuOpen && (
            <div className="md:hidden border-t border-gray-100 py-4">
              <div className="space-y-3">
                <a href="#" className="block text-gray-700 hover:text-gray-900">Features</a>
                <a href="#" className="block text-gray-700 hover:text-gray-900">How it works</a>
                <a href="#" className="block text-gray-700 hover:text-gray-900">Insights</a>
                <a href="#" className="block text-gray-700 hover:text-gray-900">Help</a>
              </div>
            </div>
          )}
        </div>
      </nav>
    );
  };

  export default Navigation