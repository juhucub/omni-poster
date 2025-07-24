import React from 'react';
import { Mail, Phone } from 'lucide-react';

const ContactSection: React.FC = () => {
    return (
      <section className="bg-gray-900 text-white py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <span className="text-sm font-semibold text-blue-400 uppercase tracking-wide">
              We'd love to hear from you
            </span>
            <h2 className="text-4xl font-bold mt-4 mb-6">
              Let's build something amazing
            </h2>
            <p className="text-xl text-gray-300">
              Have a question or idea? Reach out and let's make your next project happen.
            </p>
          </div>
  
          <div className="grid md:grid-cols-2 gap-8">
            <div className="bg-gray-800 rounded-xl p-8">
              <div className="text-blue-400 mb-6">
                <Mail className="w-12 h-12" />
              </div>
              <h3 className="text-xl font-bold mb-4">Email me</h3>
              <p className="text-gray-300 mb-4">Send me your thoughts or questions.</p>
              <a href="mailto:imnotputtingmyemailonapublicnonsecureserver@gmail.com" className="text-blue-400 hover:text-blue-300">
                imnotputtingmyemailonapublicnonsecureserver@gmail.com
              </a>
            </div>
  
            <div className="bg-gray-800 rounded-xl p-8">
              <div className="text-blue-400 mb-6">
                <Phone className="w-12 h-12" />
              </div>
              <h3 className="text-xl font-bold mb-4">Give me a call</h3>
              <p className="text-gray-300 mb-4">I'm here sometimes.</p>
              <a href="tel:+yeahyouwishyouhadmyphonenumber" className="text-blue-400 hover:text-blue-300">
              +yeahyouwishyouhadmyphonenumber
              </a>
            </div>
          </div>
        </div>
      </section>
    );
  };

  export default ContactSection;