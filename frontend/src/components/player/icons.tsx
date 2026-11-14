import type { ReactNode } from "react";

/** White, 24-unit icons for the player's controls, sized by the button around them. */
function Glyph({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" className="size-full" fill="currentColor" aria-hidden>
      {children}
    </svg>
  );
}

export const PlayGlyph = () => (
  <Glyph>
    <path d="M8 5.14v13.72L19 12 8 5.14z" />
  </Glyph>
);

export const PauseGlyph = () => (
  <Glyph>
    <path d="M7 5h3.5v14H7zm6.5 0H17v14h-3.5z" />
  </Glyph>
);

export const ReplayGlyph = () => (
  <Glyph>
    <path d="M12 5V2L7.5 6.5 12 11V7a5 5 0 1 1-5 5H5a7 7 0 1 0 7-7z" />
  </Glyph>
);

export const NextGlyph = () => (
  <Glyph>
    <path d="M6 18l8.5-6L6 6v12zm10-12v12h2V6h-2z" />
  </Glyph>
);

export const VolumeHighGlyph = () => (
  <Glyph>
    <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 7.97v8.05A4.47 4.47 0 0 0 16.5 12zM14 3.23v2.06a7 7 0 0 1 0 13.42v2.06a9 9 0 0 0 0-17.54z" />
  </Glyph>
);

export const VolumeLowGlyph = () => (
  <Glyph>
    <path d="M5 9v6h4l5 5V4L9 9H5zm13.5 3A4.5 4.5 0 0 0 16 7.97v8.05A4.47 4.47 0 0 0 18.5 12z" />
  </Glyph>
);

export const VolumeOffGlyph = () => (
  <Glyph>
    <path d="M16.5 12A4.5 4.5 0 0 0 14 7.97v2.21l2.45 2.45c.03-.2.05-.41.05-.63zM19 12c0 .94-.2 1.82-.54 2.64l1.51 1.51A8.8 8.8 0 0 0 21 12a9 9 0 0 0-7-8.77v2.06A7 7 0 0 1 19 12zM4.27 3 3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06a9 9 0 0 0 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4 9.91 6.09 12 8.18V4z" />
  </Glyph>
);

export const SettingsGlyph = () => (
  <Glyph>
    <path d="M19.43 12.98c.04-.32.07-.64.07-.98s-.03-.66-.07-.98l2.11-1.65a.5.5 0 0 0 .12-.64l-2-3.46a.5.5 0 0 0-.61-.22l-2.49 1a7.3 7.3 0 0 0-1.69-.98l-.38-2.65A.49.49 0 0 0 14 2h-4a.49.49 0 0 0-.49.42l-.38 2.65c-.61.25-1.17.59-1.69.98l-2.49-1a.5.5 0 0 0-.61.22l-2 3.46a.49.49 0 0 0 .12.64l2.11 1.65c-.04.32-.07.65-.07.98s.03.66.07.98l-2.11 1.65a.5.5 0 0 0-.12.64l2 3.46c.12.22.39.3.61.22l2.49-1c.52.4 1.08.73 1.69.98l.38 2.65c.03.24.24.42.49.42h4c.25 0 .46-.18.49-.42l.38-2.65c.61-.25 1.17-.59 1.69-.98l2.49 1c.23.09.49 0 .61-.22l2-3.46a.5.5 0 0 0-.12-.64l-2.11-1.65zM12 15.5a3.5 3.5 0 1 1 0-7 3.5 3.5 0 0 1 0 7z" />
  </Glyph>
);

export const TheaterGlyph = () => (
  <Glyph>
    <path d="M19 7H5a2 2 0 0 0-2 2v6c0 1.1.9 2 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2zm0 8H5V9h14v6z" />
  </Glyph>
);

export const DefaultViewGlyph = () => (
  <Glyph>
    <path d="M18 6H6a2 2 0 0 0-2 2v8c0 1.1.9 2 2 2h12a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2zm0 10H6V8h12v8z" />
  </Glyph>
);

export const FullscreenGlyph = () => (
  <Glyph>
    <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z" />
  </Glyph>
);

export const ExitFullscreenGlyph = () => (
  <Glyph>
    <path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z" />
  </Glyph>
);

export const RewindGlyph = () => (
  <Glyph>
    <path d="M11 18V6l-8.5 6 8.5 6zm.5-6 8.5 6V6l-8.5 6z" />
  </Glyph>
);

export const ForwardGlyph = () => (
  <Glyph>
    <path d="M4 18l8.5-6L4 6v12zm9-12v12l8.5-6L13 6z" />
  </Glyph>
);

export const CheckGlyph = () => (
  <Glyph>
    <path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
  </Glyph>
);

export const ChevronGlyph = ({ back = false }: { back?: boolean }) => (
  <Glyph>
    <path
      d={
        back
          ? "M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z"
          : "M8.59 16.59 10 18l6-6-6-6-1.41 1.41L13.17 12z"
      }
    />
  </Glyph>
);
