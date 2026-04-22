const tailwindPostcss = require('@tailwindcss/postcss');

module.exports = {
  style: {
    postcss: {
      mode: 'extends',
      plugins: [tailwindPostcss()],
    },
  },
};
