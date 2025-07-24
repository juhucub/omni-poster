import React from 'react';



const Footer: React.FC = () => {
    const footerLinks = {
      Platform: ['Home', 'Upload', 'Schedule', 'Track', 'Help'],
      Features: ['Video', 'Tags', 'Accounts', 'Queue', 'Files'],
      Resources: ['Docs', 'API', 'Guides', 'Blog', 'Status'],
      Company: ['About', 'Team', 'Careers', 'Contact', 'Legal']
    };
  
    const socialIcons = [
      { icon: 'facebook.svg', href: '#' },
      { icon: 'instagram.svg', href: '#' },
      { icon: 'youtube.svg', href: '#' },
    ];
  
    return (
      <footer className="bg-gray-900 text-white py-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-12">
            {Object.entries(footerLinks).map(([category, links]) => (
              <div key={category}>
                <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-4">
                  {category}
                </h3>
                <ul className="space-y-3">
                  {links.map((link) => (
                    <li key={link}>
                      <a href="#" className="text-gray-300 hover:text-white transition-colors">
                        {link}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
  
          <div className="border-t border-gray-800 pt-8 flex flex-col md:flex-row justify-between items-center">
            <div className="text-gray-400 text-sm mb-4 md:mb-0">
              All rights reserved © 2025 Omniposter
            </div>
            
            <div className="flex items-center space-x-3 mb-4 md:mb-0">
              <div className="w-8 h-8 bg-white rounded-lg flex items-center justify-center">
                <svg width="20" height="20" viewBox="0 0 33 33" className="text-gray-900">
                  <path d="M28,0H5C2.24,0,0,2.24,0,5v23c0,2.76,2.24,5,5,5h23c2.76,0,5-2.24,5-5V5c0-2.76-2.24-5-5-5ZM29,17c-6.63,0-12,5.37-12,12h-1c0-6.63-5.37-12-12-12v-1c6.63,0,12-5.37,12-12h1c0,6.63,5.37,12,12,12v1Z" fill="currentColor"/>
                </svg>
              </div>
              <span className="text-xl font-bold uppercase">Omniposter</span>
            </div>
  
            <div className="flex space-x-4">
              {socialIcons.map(({ icon: Icon, href }, index) => (
                <a
                  key={index}
                  href={href}
                  className="text-gray-400 hover:text-white transition-colors"
                >
                  <Icon className="w-5 h-5" />
                </a>
              ))}
            </div>
          </div>
        </div>
      </footer>
    );
  };

  export default Footer;