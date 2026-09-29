type P = { className?: string };
const base = "h-[18px] w-[18px] shrink-0";
const svg = (className: string | undefined, d: React.ReactNode) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className ?? base} aria-hidden="true">
    {d}
  </svg>
);

export const HomeIcon = ({ className }: P) => svg(className, <path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />);
export const FlameIcon = ({ className }: P) =>
  svg(className, <path d="M12 3s5 4.5 5 10a5 5 0 0 1-10 0c0-2.5 1.5-4 1.5-4S9 12 11 12c0-4 1-9 1-9z" />);
export const SearchIcon = ({ className }: P) => svg(className, <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>);
export const InfoIcon = ({ className }: P) => svg(className, <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>);
export const LayersIcon = ({ className }: P) => svg(className, <path d="m12 3 9 5-9 5-9-5 9-5zm-9 9 9 5 9-5M3 16l9 5 9-5" />);
export const DocIcon = ({ className }: P) => svg(className, <path d="M7 3h7l5 5v13H7zM14 3v5h5" />);
export const ExternalIcon = ({ className }: P) => svg(className, <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />);
export const UsersIcon = ({ className }: P) =>
  svg(className, <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4-6" /></>);
export const ChatIcon = ({ className }: P) => svg(className, <path d="M4 5h16v11H9l-5 4z" />);
export const ArrowUpIcon = ({ className }: P) => svg(className, <path d="M12 19V5M5 12l7-7 7 7" />);
export const HashIcon = ({ className }: P) => svg(className, <path d="M5 9h14M4 15h14M10 3 8 21M16 3l-2 18" />);
