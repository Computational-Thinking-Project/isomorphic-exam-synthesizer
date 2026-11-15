/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: '#fafafa',
        surface: '#ffffff',
        rail: '#f4f4f5',
        line: '#e4e4e7',
        ink: '#3f3f46',
        strong: '#27272a',
        muted: '#6b6b74',
        'control-border': '#85858f',
        highlight: '#304c70',
        accent: {
          DEFAULT: '#f5ce58',
          soft: '#fef7dd',
          border: '#f0d26b',
          ink: '#5e4a12',
        },
        support: {
          bg: '#edf1f7',
          line: '#d7e0ec',
          text: '#52647b',
        },
        approved: {
          bg: '#eaf5ed',
          ink: '#255c3b',
          border: '#b7d8c1',
        },
        danger: {
          DEFAULT: '#a32b32',
          soft: '#fff1f2',
          border: '#fecdd3',
        },
      },
      boxShadow: {
        soft: '0 1px 3px rgba(39, 39, 42, 0.04)',
        paper: '0 6px 16px rgba(39, 39, 42, 0.05)',
        card: '0 2px 8px rgba(39, 39, 42, 0.06)',
      },
    },
  },
  plugins: [],
}
