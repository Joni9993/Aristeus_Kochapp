/** @type {import('tailwindcss').Config} */
export default {
  // Theme is resolved into data-theme="light|dark" on <html> (pre-paint
  // script in index.html + useTheme hook; 'system' follows the OS). `dark:`
  // variants and the CSS-variable palette both key off that attribute, so
  // the manual override under "Mehr" affects everything consistently.
  darkMode: ['selector', '[data-theme="dark"]'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        display: ['"Fraunces Variable"', 'Fraunces', 'ui-serif', 'Georgia', 'serif'],
      },
      colors: {
        surface: 'rgb(var(--surface) / <alpha-value>)',
        card: 'rgb(var(--card) / <alpha-value>)',
        ink: 'rgb(var(--ink) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        line: 'rgb(var(--line) / <alpha-value>)',
        olive: {
          DEFAULT: 'rgb(var(--olive) / <alpha-value>)',
          hover: 'rgb(var(--olive-hover) / <alpha-value>)',
          soft: 'rgb(var(--olive-soft) / <alpha-value>)',
          on: 'rgb(var(--olive-on) / <alpha-value>)',
        },
        honey: {
          DEFAULT: 'rgb(var(--honey) / <alpha-value>)',
          soft: 'rgb(var(--honey-soft) / <alpha-value>)',
        },
      },
    },
  },
  plugins: [],
}
