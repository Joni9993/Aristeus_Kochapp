// Small decorative laurel sprig used next to the "Aristeus" wordmark —
// a nod to Aristaios (bee-keeping, olive groves). Single-color (currentColor)
// so it inherits whatever text color the header uses, in both themes.
export default function Laurel({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M12 21c0-6 2-10 6-13"
        stroke="currentColor"
        strokeWidth={1.4}
        strokeLinecap="round"
      />
      <path
        d="M12.8 17.2c1.6.2 3-.2 4-1.1M13.6 13.6c1.5.3 2.8 0 3.8-.8M14.6 10c1.4.4 2.6.2 3.5-.5M15.8 6.7c1.1.4 2.1.3 2.9-.3"
        stroke="currentColor"
        strokeWidth={1.2}
        strokeLinecap="round"
      />
      <path
        d="M10.6 18.6c-1.6.4-3 .1-4.1-.7M10.4 14.9c-1.5.5-2.8.3-3.9-.4M10.8 11.2c-1.4.5-2.6.4-3.6-.2M12 8c-1.2.6-2.2.6-3.1.1"
        stroke="currentColor"
        strokeWidth={1.2}
        strokeLinecap="round"
      />
    </svg>
  )
}
