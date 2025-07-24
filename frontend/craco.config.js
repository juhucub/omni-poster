const tailwindPostcss = require('@tailwindcss/postcss');
const autoprefixer    = require('autoprefixer');

module.exports = {
  style: {
    postcss: {
      mode: 'extends',           // ← merge with CRA’s default PostCSS rule
      plugins: [
        tailwindPostcss(),       // ← your Tailwind adapter
        autoprefixer(),          // ← autoprefixer as usual
      ],
    },
  },
};