import React from 'react';

const Promo = () => {
  return (
    <section className="bg-gradient-to-r from-purple-500 to-indigo-600 text-white rounded-lg shadow-lg p-6 flex flex-col md:flex-row items-center justify-between">
      <div className="mb-4 md:mb-0">
        <h3 className="text-2xl font-bold">Upgrade to PRO</h3>
        <p className="text-sm mt-2 max-w-md">
          Upgrade your account to Pro and enjoy unlimited features.
        </p>
        <button className="mt-4 px-6 py-2 bg-white text-purple-600 font-semibold rounded-full shadow hover:bg-gray-100">
          Upgrade
        </button>
      </div>
      <div className="w-32 h-32 md:w-48 md:h-48">
        <img
          src="url-to-illustration"
          alt="Upgrade Illustration"
          className="w-full h-full object-contain"
        />
      </div>
    </section>
  );
};

export default Promo;
