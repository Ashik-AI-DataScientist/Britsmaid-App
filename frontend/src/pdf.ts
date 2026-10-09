import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { LOGO_URL } from "@/src/api";
import { fmtDate, inr, monthLabel } from "@/src/format";

const esc = (s: any) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] as string);

const shell = (title: string, body: string) => `<!doctype html><html><head><meta charset="utf-8"/><title>${esc(title)}</title>
<style>body{font-family:Helvetica,Arial,sans-serif;color:#111827;margin:32px;font-size:13px}h1{color:#1B3A6B;margin:0;font-size:26px}
.top{display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid #1B3A6B;padding-bottom:16px;margin-bottom:20px}
.logo{width:90px;height:90px;object-fit:contain}table{width:100%;border-collapse:collapse;margin-top:12px}th{background:#E8EDF4;color:#1B3A6B;text-align:left;padding:8px}
td{padding:8px;border-bottom:1px solid #E5E7EB}.r{text-align:right}.muted{color:#6B7280}.tot td{font-weight:bold;font-size:15px;border-top:2px solid #1B3A6B}
.box{background:#F3F4F6;border-radius:8px;padding:12px;margin:12px 0}.big{font-size:28px;color:#1B3A6B;font-weight:bold}.grid{display:flex;gap:24px}</style></head>
<body>${body}<p class="muted" style="margin-top:32px;text-align:center">Britsmaid Property Management · Thank you for your partnership</p></body></html>`;

export function invoiceHtml(inv: any) {
  const rows = inv.items.map((i: any) => `<tr><td>${esc(i.description)}</td><td class="r">${i.qty}</td><td class="r">${inr(i.rate)}</td><td class="r">${inr(i.qty * i.rate)}</td></tr>`).join("");
  return shell(inv.number, `<div class="top"><div><h1>INVOICE</h1><div class="muted">${esc(inv.number)} · ${inv.type === "guest" ? "Guest stay" : "Client services"}</div></div><img class="logo" src="${LOGO_URL}"/></div>
<div class="grid"><div style="flex:1"><b>Bill to</b><br/>${esc(inv.bill_to_name)}<br/>${esc(inv.bill_to_address)}<br/>${esc(inv.bill_to_email)} ${esc(inv.bill_to_phone)}</div>
<div style="flex:1"><b>Issued:</b> ${fmtDate(inv.issue_date)}<br/>${inv.due_date ? `<b>Due:</b> ${fmtDate(inv.due_date)}<br/>` : ""}${inv.property_name ? `<b>Property:</b> ${esc(inv.property_name)}<br/>` : ""}<b>Status:</b> ${inv.status.toUpperCase()}</div></div>
<table><tr><th>Description</th><th class="r">Qty</th><th class="r">Rate</th><th class="r">Amount</th></tr>${rows}
<tr><td colspan="3" class="r">Subtotal</td><td class="r">${inr(inv.subtotal)}</td></tr>
${inv.discount ? `<tr><td colspan="3" class="r">Discount</td><td class="r">-${inr(inv.discount)}</td></tr>` : ""}
${inv.tax_percent ? `<tr><td colspan="3" class="r">GST (${inv.tax_percent}%)</td><td class="r">${inr(inv.tax_amount)}</td></tr>` : ""}
<tr class="tot"><td colspan="3" class="r">Total</td><td class="r">${inr(inv.total)}</td></tr></table>
${inv.notes ? `<div class="box">${esc(inv.notes)}</div>` : ""}`);
}

export function settlementHtml(s: any, extra?: { title?: string; notes?: string; photos?: string[] }) {
  const ota = s.by_ota.map((o: any) => `<tr><td>${esc(o.ota)}</td><td class="r">${o.bookings}</td><td class="r">${o.nights}</td><td class="r">${inr(o.gross)}</td><td class="r">-${inr(o.commission)}</td><td class="r">${inr(o.net)}</td></tr>`).join("");
  const bk = s.bookings.map((b: any) => `<tr><td>${esc(b.guest_name)}</td><td>${esc(b.ota)}</td><td>${fmtDate(b.check_in)} → ${fmtDate(b.check_out)}</td><td class="r">${inr(b.amount)}</td></tr>`).join("");
  const photos = (extra?.photos ?? []).map((u) => `<img src="${u}" style="width:31%;margin:1%;border-radius:6px;aspect-ratio:1;object-fit:cover"/>`).join("");
  return shell("Owner statement", `<div class="top"><div><h1>${esc(extra?.title || "Owner Statement")}</h1><div class="muted">${esc(s.property_name)} · ${esc(s.owner_name)} · ${monthLabel(s.month)}</div></div><img class="logo" src="${LOGO_URL}"/></div>
<div class="box"><div class="muted">Owner payout</div><div class="big">${inr(s.owner_payout)}</div><div class="muted">${s.nights} nights · ${s.occupancy_percent}% occupancy · Split ${s.owner_share_percent}% owner / ${s.britsmaid_share_percent}% Britsmaid</div></div>
<table><tr><th>Calculation</th><th class="r">Amount</th></tr><tr><td>Gross booking revenue</td><td class="r">${inr(s.gross)}</td></tr><tr><td>OTA commissions</td><td class="r">-${inr(s.ota_commission)}</td></tr>
<tr><td>Net revenue</td><td class="r">${inr(s.net_revenue)}</td></tr><tr><td>Owner share (${s.owner_share_percent}%)</td><td class="r">${inr(s.owner_share)}</td></tr><tr><td>Britsmaid share (${s.britsmaid_share_percent}%)</td><td class="r">${inr(s.britsmaid_share)}</td></tr>
<tr><td>Electricity ${s.electricity_mode === "split_half" ? `(owner 50% of ${inr(s.electricity_total)})` : "(managed by owner)"}</td><td class="r">-${inr(s.owner_electricity)}</td></tr>
${s.other_deductions ? `<tr><td>Other deductions</td><td class="r">-${inr(s.other_deductions)}</td></tr>` : ""}<tr class="tot"><td>Owner payout</td><td class="r">${inr(s.owner_payout)}</td></tr></table>
<h3>Revenue by OTA</h3><table><tr><th>OTA</th><th class="r">Bookings</th><th class="r">Nights</th><th class="r">Gross</th><th class="r">Commission</th><th class="r">Net</th></tr>${ota}</table>
<h3>Bookings</h3><table><tr><th>Guest</th><th>OTA</th><th>Stay</th><th class="r">Amount</th></tr>${bk}</table>
${extra?.notes ? `<h3>Property condition</h3><div class="box">${esc(extra.notes)}</div>` : ""}${photos ? `<div>${photos}</div>` : ""}`);
}

export async function sharePdf(html: string) {
  if (Platform.OS === "web") {
    await Print.printAsync({ html });
    return;
  }
  const { uri } = await Print.printToFileAsync({ html });
  if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(uri, { mimeType: "application/pdf", UTI: "com.adobe.pdf", dialogTitle: "Share PDF" });
}
