export const inr = (v: number | undefined | null) =>
  "₹" + Math.round(v ?? 0).toLocaleString("en-IN");

const pad = (n: number) => String(n).padStart(2, "0");
export const toISO = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const todayISO = () => toISO(new Date());
export const thisMonth = () => todayISO().slice(0, 7);

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
export const monthLabel = (m: string) => {
  const [y, mm] = m.split("-").map(Number);
  return `${MONTHS[mm - 1]} ${y}`;
};
export const monthShort = (m: string) => MONTHS[Number(m.split("-")[1]) - 1].slice(0, 3);
export const shiftMonth = (m: string, delta: number) => {
  const [y, mm] = m.split("-").map(Number);
  const idx = y * 12 + (mm - 1) + delta;
  return `${Math.floor(idx / 12)}-${pad((idx % 12) + 1)}`;
};
export const fmtDate = (iso?: string) => {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${d} ${MONTHS[m - 1].slice(0, 3)} ${y}`;
};
export const fmtShort = (iso: string) => {
  const [, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${d} ${MONTHS[m - 1].slice(0, 3)}`;
};
export const nightsBetween = (a: string, b: string) =>
  Math.max(0, Math.round((new Date(b + "T00:00:00").getTime() - new Date(a + "T00:00:00").getTime()) / 86400000));
export const addDays = (iso: string, n: number) => {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + n);
  return toISO(d);
};

// Third-party OTA brand colors (stay identical across themes)
export const OTA_COLORS: Record<string, string> = {
  Airbnb: "#FF5A5F",
  "Booking.com": "#003580",
  Agoda: "#7B3FA0",
  MakeMyTrip: "#F97316",
  Expedia: "#F5B70A",
  Vrbo: "#1E64C8",
  Direct: "#10B981",
  Other: "#6B7280",
};
export const OTAS = Object.keys(OTA_COLORS);
export const otaColor = (o: string) => OTA_COLORS[o] ?? OTA_COLORS.Other;
