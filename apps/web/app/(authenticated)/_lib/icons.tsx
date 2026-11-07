import type { ReactNode } from "react";

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}

/* Dashboard / shared icons (used in multiple places). */
export const IconCalendar = () => <Icon><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M16 2v4M8 2v4M3 9h18" /></Icon>;
export const IconUsers = () => <Icon><circle cx="9" cy="8" r="3.6" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M15.5 4.9a3.6 3.6 0 0 1 0 6.2" /><path d="M17.6 14.5a6.5 6.5 0 0 1 4 5.5" /></Icon>;
export const IconFile = () => <Icon><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6" /><path d="M9 13h6M9 17h6" /></Icon>;
export const IconCheck = () => <Icon><circle cx="12" cy="12" r="9" /><path d="m8.5 12.3 2.4 2.4 4.8-5.2" /></Icon>;
export const IconPlus = () => <Icon><path d="M12 5v14M5 12h14" /></Icon>;
export const IconUser = () => <Icon><circle cx="12" cy="8" r="4" /><path d="M4.5 21a7.5 7.5 0 0 1 15 0" /></Icon>;
export const IconPen = () => <Icon><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></Icon>;
export const IconCard = () => <Icon><rect x="2" y="5" width="20" height="14" rx="2" /><path d="M2 10h20" /></Icon>;
export const IconChart = () => <Icon><path d="M3 3v18h18" /><path d="M8 17v-6M13 17V7M18 17v-4" /></Icon>;
export const IconFlag = () => <Icon><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1Z" /><path d="M4 22v-7" /></Icon>;
export const IconAlert = () => <Icon><path d="M12 2 1 21h22L12 2z" /><path d="M12 10v5M12 18h.01" /></Icon>;

/* Sidebar nav icons (replace unicode glyphs). */
export const IconHome = () => <Icon><path d="M3 11 12 3l9 8" /><path d="M5 10v10h14V10" /></Icon>;
export const IconLead = () => <Icon><path d="M3 5h8l2 3h8v10a2 2 0 0 1-2 2H3z" /><path d="m9 13 3 3 3-3" /><path d="M12 10v6" /></Icon>;
export const IconQueue = () => <Icon><path d="M4 6h16M4 12h16M4 18h10" /></Icon>;
export const IconFollowUp = () => <Icon><path d="M4 4h12l4 4v12H4z" /><path d="m9 13 2 2 4-4" /></Icon>;
export const IconStethoscope = () => <Icon><path d="M6 3v6a4 4 0 0 0 8 0V3" /><path d="M4 3h2M14 3h2" /><path d="M10 13v4a4 4 0 0 0 8 0" /><circle cx="18" cy="17" r="2" /></Icon>;
export const IconBuilding = () => <Icon><path d="M4 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16" /><path d="M16 9h3a2 2 0 0 1 2 2v10" /><path d="M8 7h4M8 11h4M8 15h4" /></Icon>;
export const IconGrid = () => <Icon><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></Icon>;
export const IconMedical = () => <Icon><path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z" /></Icon>;
export const IconReceipt = () => <Icon><path d="M4 2v20l3-2 3 2 3-2 3 2 3-2V2z" /><path d="M8 7h8M8 11h8M8 15h6" /></Icon>;
export const IconSigma = () => <Icon><path d="M6 4h12v3l-6 5 6 5v3H6" /></Icon>;
export const IconBox = () => <Icon><path d="M21 8 12 3 3 8v8l9 5 9-5z" /><path d="m3 8 9 5 9-5" /><path d="M12 13v8" /></Icon>;
export const IconReport = () => <Icon><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></Icon>;
export const IconInventory = () => <Icon><path d="M4 7h16v4H4z" /><path d="M5 11v9h14v-9" /><path d="M10 14h4" /></Icon>;
export const IconGlobe = () => <Icon><circle cx="12" cy="12" r="9" /><path d="M3 12h18" /><path d="M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></Icon>;
export const IconContent = () => <Icon><path d="M4 4h16v12H5l-3 4z" /><path d="M8 9h8M8 12h5" /></Icon>;
export const IconAt = () => <Icon><circle cx="12" cy="12" r="4" /><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8" /></Icon>;
export const IconImage = () => <Icon><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="9" r="1.6" /><path d="m21 17-5-5-9 9" /></Icon>;
export const IconTrend = () => <Icon><path d="M3 17 9 11l4 4 8-9" /><path d="M14 6h7v7" /></Icon>;
export const IconSettings = () => <Icon><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3h.1a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8v.1a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z" /></Icon>;
export const IconBell = () => <Icon><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10 21a2 2 0 0 0 4 0" /></Icon>;
export const IconLock = () => <Icon><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></Icon>;
export const IconShield = () => <Icon><path d="M12 2 4 5v7c0 5 3.5 8 8 10 4.5-2 8-5 8-10V5z" /></Icon>;
export const IconStar = () => <Icon><path d="m12 2 3 7 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z" /></Icon>;
