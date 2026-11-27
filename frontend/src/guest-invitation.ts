import { fmtDate } from './format';

type StayInvitation = { guest_name?: string; property_name: string; check_in: string; check_out: string };
const line = (value?: string) => (value || '').replace(/\s+/g, ' ').trim();

export function guestUploadMessage(stay: StayInvitation, url: string): string {
  const link = new URL(url);
  if (!['https:', 'http:'].includes(link.protocol) || link.pathname !== '/guest-check-in'
      || !new URLSearchParams(link.hash.slice(1)).get('invite')) {
    throw new Error('The guest upload link is incomplete. Please get a new link before sharing.');
  }
  return `Hi ${line(stay.guest_name) || 'there'},\n\nProperty: ${line(stay.property_name)}\nStay: ${fmtDate(stay.check_in)} to ${fmtDate(stay.check_out)}\n\nPlease upload an ID for every guest using the link below. You can upload all IDs yourself, or upload yours and forward this message to the rest of your group so they can upload theirs. No app or login is needed.\n\n${url}\n\nThank you,\nTeam Britsmaid`;
}
