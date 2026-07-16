/** @type {import('tailwindcss').Config} */
export default {
  // No manual toggle — the app follows the OS color-scheme. This keeps
  // `dark:` variants available (for the handful of literal-color
  // exceptions like error red) driven by prefers-color-scheme, while the
  // branded palette below is CSS-variable based and switches automatically.
  darkMode: 'media',
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
