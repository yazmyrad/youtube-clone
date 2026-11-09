import type { ReactNode, SVGProps } from "react";

function Icon({ children, ...props }: SVGProps<SVGSVGElement> & { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor" aria-hidden {...props}>
      {children}
    </svg>
  );
}

export const MenuIcon = () => (
  <Icon>
    <path d="M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z" />
  </Icon>
);

export const SearchIcon = () => (
  <Icon>
    <path d="M15.5 14h-.8l-.3-.3A6.5 6.5 0 1 0 14 14.4l.3.3v.8l5 5 1.5-1.5-5.3-5zm-6 0a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9z" />
  </Icon>
);

export const HomeIcon = () => (
  <Icon>
    <path d="M12 3 3 10.5V21h6v-6h6v6h6V10.5z" />
  </Icon>
);

export const AccountIcon = () => (
  <Icon>
    <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 4a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7zm0 14a8 8 0 0 1-6.2-3c.9-1.7 3.7-3 6.2-3s5.3 1.3 6.2 3a8 8 0 0 1-6.2 3z" />
  </Icon>
);

export const PlusIcon = () => (
  <Icon>
    <path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z" />
  </Icon>
);

export const UploadIcon = () => (
  <Icon width="48" height="48">
    <path d="M11 16V7.8L8.4 10.4 7 9l5-5 5 5-1.4 1.4L13 7.8V16zM5 18h14v2H5z" />
  </Icon>
);

export function Logo() {
  return (
    <span className="flex items-center gap-1.5">
      <svg viewBox="0 0 24 24" width="28" height="28" aria-hidden>
        <circle cx="12" cy="12" r="12" className="fill-brand" />
        <path d="M9.5 7.5v9l7-4.5z" fill="#fff" />
      </svg>
      <span className="text-lg font-medium tracking-tight">YouTube clone</span>
    </span>
  );
}
