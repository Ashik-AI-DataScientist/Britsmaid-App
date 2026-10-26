export const CLEANING_COMPLETE_COLOR = "#000000";
export const CLEANING_COMPLETE_SOFT = "#FFFFFF";
export const CLEANING_COMPLETE_MARKER = { backgroundColor: CLEANING_COMPLETE_SOFT, borderColor: CLEANING_COMPLETE_COLOR, borderWidth: 1, borderRadius: 0 };
export const CLEANING_REFRESH_KEYS = ["cleaning", "dashboard", "properties", "property", "owner-dashboard", "calendar"];

export function refreshCleaningViews(client: { invalidateQueries: (filter: { queryKey: string[] }) => unknown }) {
  for (const key of CLEANING_REFRESH_KEYS) client.invalidateQueries({ queryKey: [key] });
}

// Pending work wins on a day with several tasks; cancelled work is not due.
export function cleaningDayStatus(tasks: { status: string }[]): "pending" | "completed" | undefined {
  const active = tasks.filter(task => task.status !== "cancelled");
  if (!active.length) return undefined;
  return active.every(task => task.status === "completed") ? "completed" : "pending";
}
