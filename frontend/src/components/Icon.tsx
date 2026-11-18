/**
 * 单一线性图标族（DESIGN.md §6）：1.5px 描边、圆角端点，尺寸 16/20/24 三档。
 * 全部为几何线性图标，禁用 Emoji 与面性图标。
 */
import type { ReactNode, SVGProps } from "react";

export type IconName =
  | "star"
  | "plus"
  | "upload"
  | "trash"
  | "history"
  | "search"
  | "play"
  | "queue"
  | "check"
  | "alert"
  | "spinner"
  | "file"
  | "quote"
  | "chevron-down"
  | "chevron-right"
  | "close"
  | "clock"
  | "film"
  | "layers";

interface IconProps extends SVGProps<SVGSVGElement> {
  name: IconName;
  size?: 16 | 20 | 24;
}

const PATHS: Record<IconName, ReactNode> = {
  star: <path d="M12 3.5l2.6 5.3 5.9.9-4.2 4.1 1 5.8-5.3-2.8-5.3 2.8 1-5.8L3.5 9.7l5.9-.9L12 3.5z" />,
  plus: (
    <>
      <path d="M12 5v14" />
      <path d="M5 12h14" />
    </>
  ),
  upload: (
    <>
      <path d="M12 16V4" />
      <path d="M6.5 9.5L12 4l5.5 5.5" />
      <path d="M4 17v2a1.5 1.5 0 0 0 1.5 1.5h13A1.5 1.5 0 0 0 20 19v-2" />
    </>
  ),
  trash: (
    <>
      <path d="M4 7h16" />
      <path d="M9 7V5a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 5v2" />
      <path d="M6 7l1 13a1.5 1.5 0 0 0 1.5 1.4h7A1.5 1.5 0 0 0 17 20l1-13" />
      <path d="M10 11v6M14 11v6" />
    </>
  ),
  history: (
    <>
      <path d="M3.5 12a8.5 8.5 0 1 1 2.5 6" />
      <path d="M3.5 12H2" />
      <path d="M3.5 12l1.5-1.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16 16l4.5 4.5" />
    </>
  ),
  play: <path d="M8 5.5v13l11-6.5-11-6.5z" />,
  queue: (
    <>
      <path d="M4 6h16M4 12h16M4 18h10" />
      <circle cx="18.5" cy="18" r="2" />
    </>
  ),
  check: <path d="M4.5 12.5l5 5L19.5 7" />,
  alert: (
    <>
      <path d="M12 4L2.5 20h19L12 4z" />
      <path d="M12 10v4.5" />
      <circle cx="12" cy="17.2" r="0.1" />
    </>
  ),
  spinner: (
    <>
      <path d="M12 3.5a8.5 8.5 0 1 1-8.5 8.5" />
      <path d="M12 3.5v4" />
    </>
  ),
  file: (
    <>
      <path d="M6 3.5h8L19 8.5v12A1.5 1.5 0 0 1 17.5 22h-11A1.5 1.5 0 0 1 5 20.5v-15A1.5 1.5 0 0 1 6.5 3.5z" transform="translate(0.5 -1.5)" />
      <path d="M13.5 3.5v5h5" />
    </>
  ),
  quote: (
    <>
      <path d="M5 16.5c-1 0-2-1-2-2.7C3 9.6 5.4 7 9 6l.7 1.6C7.4 8.4 6.2 9.7 6 11.2c.2-.1.5-.2.8-.2a2.2 2.2 0 1 1-1.8 5.5z" />
      <path d="M14.5 16.5c-1 0-2-1-2-2.7 0-4.2 2.4-6.8 6-7.8l.7 1.6c-2.3.8-3.5 2.1-3.7 3.6.2-.1.5-.2.8-.2a2.2 2.2 0 1 1-1.8 5.5z" />
    </>
  ),
  "chevron-down": <path d="M5.5 8.5l6.5 6.5 6.5-6.5" />,
  "chevron-right": <path d="M9.5 5.5L16 12l-6.5 6.5" />,
  close: (
    <>
      <path d="M6 6l12 12" />
      <path d="M18 6L6 18" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7v5l3.5 2" />
    </>
  ),
  film: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M7.5 5v14M16.5 5v14M3 9.5h4.5M3 14.5h4.5M16.5 9.5H21M16.5 14.5H21" />
    </>
  ),
  layers: (
    <>
      <path d="M12 3.5l9 4.5-9 4.5-9-4.5 9-4.5z" />
      <path d="M3 12.5l9 4.5 9-4.5" />
    </>
  ),
};

export function Icon({ name, size = 16, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {PATHS[name]}
    </svg>
  );
}
