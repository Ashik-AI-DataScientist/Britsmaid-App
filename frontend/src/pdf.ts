import { money, percentAmount } from "@/src/booking-finance";
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { LOGO_URL } from "@/src/api";
import { fmtDate, inr, monthLabel } from "@/src/format";
import { reportPresentation } from '@/src/expense-presentation';

const esc = (s: any) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] as string);

const amountRow = (label: string, value: any, deduction = false, strong = false) => `<tr${strong ? ' class="tot"' : ''}><td>${label}</td><td class="r">${value == null ? 'Not recorded' : `${deduction ? '-' : ''}${inr(value)}`}</td></tr>`;
function calculationRows(s: any) {
  const p = reportPresentation(s);
  return amountRow('Gross guest payments', s.gross)
    + (p.bookingDeductions ? amountRow('Booking deductions', p.bookingDeductions, true) : '')
    + (p.before > 0 ? amountRow('Expenses before revenue split', p.before, true) : '')
    + (s.net_revenue != null ? amountRow('Revenue available to split', s.net_revenue) : '')
    + amountRow(`Owner allocated share (${esc(s.owner_share_percent)}%)`, s.owner_share)
    + (p.ownerAfter > 0 ? amountRow('Owner expenses after split', p.ownerAfter, true) : '')
    + (s.owner_before_tds != null ? amountRow('Owner balance before TDS', s.owner_before_tds) : '')
    + (s.owner_tds_percent || s.owner_tds ? amountRow(`Owner TDS (${esc(s.owner_tds_percent || 2)}%) · monthly total`, s.owner_tds, true) : '')
    + amountRow('Owner final payout', s.owner_payout ?? s.calculated_payout, false, true);
}
function supportingRows(s: any) {
  const p = reportPresentation(s);
  const taxes = [['OTA commissions', s.ota_commission], ['Booking GST', s.gst_total], ['Other tax deductions', s.platform_tax]]
    .filter(([, value]) => value).map(([label, value]) => amountRow(String(label), value)).join('');
  const expenses = p.groups.map(g => `<h4>${g.label} · ${inr(g.total)}</h4>${g.mismatch ? '<p>Saved expense totals differ from the available details. Ask the admin to review this statement.</p>' : ''}
    <table><tr><th>Expense and note</th><th>Treatment / allocation</th><th class="r">Full expense</th></tr>${g.items.map((d: any) => {
      const a = d.allocation || {};
      const owner = a.owner_amount ?? d.owner_amount, bm = a.britsmaid_amount ?? d.britsmaid_amount;
      const shares = [owner > 0 ? `Owner${a.owner_percent != null ? ` (${esc(a.owner_percent)}%)` : ''}: ${inr(owner)}` : '', bm > 0 ? `Britsmaid${a.britsmaid_percent != null ? ` (${esc(a.britsmaid_percent)}%)` : ''}: ${inr(bm)}` : ''].filter(Boolean).join('<br>');
      const treatment = g.key === 'before_split' ? 'Before revenue split · deducted once' : g.key === 'reference' ? 'Reference only · not deducted' : `After revenue split<br>${shares || 'Allocation detail was not included in this saved statement'}`;
      return `<tr><td>${esc(d.title || 'Other expense')}<br>${esc(d.notes || 'No additional note recorded')}<br><small>${(d.media_ids || []).length ? `${d.media_ids.length} attachment(s) · view in the app` : 'No attachment recorded'}</small></td><td>${treatment}</td><td class="r">${inr(d.amount)}</td></tr>`;
    }).join('')}</table>`).join('');
  const bm = s.britsmaid_share == null ? '' : `<h3>Britsmaid breakdown</h3><table>${amountRow(`Britsmaid allocated share (${esc(s.britsmaid_share_percent)}%)`, s.britsmaid_share)}${p.bmAfter > 0 ? amountRow('Britsmaid expenses after split', p.bmAfter, true) : ''}${amountRow('Britsmaid net earnings', s.britsmaid_net, false, true)}</table>`;
  return (taxes ? `<h3>Booking deductions · details</h3><table>${taxes}</table>` : '')
    + (p.groups.length ? `<h3>Expenses</h3><p>Total reported expenses: ${inr(p.totalExpenses)}</p>${expenses}` : '') + bm;
}

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

function statementShell(title: string, body: string) {
  const html = shell(title, body);
  return html.replace('</style>', `@page{size:A4 landscape;margin:14mm;@bottom-center{content:"Britsmaid Property Management Kerala Private Limited";font-family:Arial;font-size:8px;color:#4c6075}}body{margin:0;font-size:13px;color:#162639}h1{font-size:24px}h3{color:#19365c;margin-top:22px;break-after:avoid}h4{color:#19365c;break-after:avoid}th{background:#19365c;color:white}td,th{padding:7px}tr{break-inside:avoid}.payment-section{break-inside:avoid}.booking-ledger tbody{break-inside:avoid}thead{display:table-header-group}.top{break-inside:avoid}.box{background:#19365c;color:white}.box .muted,.box .big{color:white}.booking-ledger{font-size:11px}.booking-ledger th{font-size:10px}.booking-ledger td:first-child{min-width:130px}.booking-note td{font-size:10px;color:#4c6075;padding-bottom:12px}small{font-size:10px}.r{white-space:nowrap}</style>`)
    .replace('<p class="muted" style="margin-top:32px;text-align:center">Britsmaid Property Management · Thank you for your partnership</p>', '');
}

export function settlementHtml(s: any, extra?: { title?: string; notes?: string; photos?: string[] }) {
  const ota = s.by_ota.map((o: any) => `<tr><td>${esc(o.ota)}</td><td class="r">${o.bookings}</td><td class="r">${o.nights}</td><td class="r">${inr(o.gross)}</td><td class="r">-${inr(o.commission)}</td><td class="r">${inr(o.net)}</td></tr>`).join("");
  const rate = (line: any) => line?.percent == null ? '' : `${esc(line.percent)}%`;
  const bk = (s.bookings || []).map((b: any) => {
    const f = b.financials;
    const gst = f?.gst?.amount || 0, fee = f?.platform_fee?.amount ?? b.ota_commission ?? 0;
    const tax = f?.platform_tax?.amount || 0, misc = f?.misc_amount || 0;
    const net = b.net_revenue ?? (b.amount - gst - fee - tax - misc);
    const owner = percentAmount(net, s.owner_share_percent ?? 70);
    const bm = money(net - owner);
    const cell = (amount: number, line?: any) => `<td class="r">${inr(amount)}<br><small>${rate(line)}</small></td>`;
    return `<tbody><tr><td><b>${esc(b.guest_name)}</b><br><small>${esc(b.ota)} · ${fmtDate(b.check_in)} → ${fmtDate(b.check_out)}</small></td>${cell(b.amount)}${cell(gst, f?.gst)}${cell(fee, f?.platform_fee)}${cell(tax, f?.platform_tax)}${cell(misc)}${cell(net)}${cell(owner)}${cell(bm)}</tr>`
      + `<tr class="booking-note"><td colspan="9">${f ? `${f.gst_included ? 'GST included in guest payment' : 'Guest payment includes added GST'}. Platform fee base: ${f.platform_fee?.base === 'gross' ? 'guest total' : 'amount excluding GST'}; other tax base: ${f.platform_tax?.base === 'gross' ? 'guest total' : 'amount excluding GST'}.${f.gst?.manual || f.platform_fee?.manual || f.platform_tax?.manual ? ' Includes directly entered amounts.' : ''}${misc ? ` Other booking expense: ${esc(f.misc_title)}. ${esc(f.misc_notes)}` : ''}` : 'Tax details were not recorded. Saved guest payment and OTA commission retained; no tax has been inferred.'}</td></tr></tbody>`;
  }).join('');
  const payout = s.payout;
  const payment = payout ? `<h3>Payout status: PAID</h3><table>${amountRow('Amount paid', payout.amount, false, true)}<tr><td>Paid on</td><td class="r">${esc(fmtDate(payout.paid_on))}</td></tr><tr><td>Method</td><td class="r">${esc(payout.method)}</td></tr><tr><td>Reference / UTR</td><td class="r">${esc(payout.reference || 'Not recorded')}</td></tr><tr><td>Receipt number</td><td class="r">${esc(payout.receipt_number || 'Not recorded')}</td></tr></table>${payout.notes ? `<p>Payment note: ${esc(payout.notes)}</p>` : ''}${Number(payout.amount) !== Number(s.owner_payout) ? `<p>Recorded payment differs from the current calculated payout. Payment receipt figures are retained as recorded.</p>` : ''}` : '<p>Payout pending: no owner payment has been recorded for this month.</p>';
  const photos = (extra?.photos ?? []).map((u) => `<img src="${u}" style="width:31%;margin:1%;border-radius:6px;aspect-ratio:1;object-fit:cover"/>`).join("");
  return statementShell("Owner statement", `<div class="top"><div><h1>${esc(extra?.title || "Owner Statement")}</h1><div class="muted">${esc(s.property_name)} · ${esc(s.owner_name)} · ${monthLabel(s.month)}</div></div><img class="logo" src="${LOGO_URL}"/></div>
<div class="box"><div class="muted">Owner final payout</div><div class="big">${inr(s.owner_payout)}</div><div class="muted">${s.nights} nights · ${s.occupancy_percent}% occupancy · Split ${s.owner_share_percent}% owner / ${s.britsmaid_share_percent}% Britsmaid</div></div>
<h3>How the payout is calculated</h3><table><tr><th>Calculation</th><th class="r">Amount</th></tr>${calculationRows(s)}</table>
<div class="payment-section">${payment}</div>
${supportingRows(s)}
<h3>Revenue by OTA</h3><table><tr><th>OTA</th><th class="r">Bookings</th><th class="r">Nights</th><th class="r">Gross</th><th class="r">Commission</th><th class="r">Net</th></tr>${ota}</table>
<h3>Booking-by-booking breakdown</h3><table class="booking-ledger"><thead><tr><th>Guest / channel / stay</th><th class="r">Gross</th><th class="r">GST</th><th class="r">OTA fee</th><th class="r">Other tax</th><th class="r">Other expense</th><th class="r">Net</th><th class="r">Owner</th><th class="r">Britsmaid</th></tr></thead>${bk}</table>
<p class="muted">Booking allocations use the statement split before monthly property expenses and TDS. Individually rounded allocations may differ by a few paise from the monthly split of total revenue. Property expenses and owner TDS are deducted once in the monthly calculation.</p>${extra?.notes ? `<h3>Property condition</h3><div class="box">${esc(extra.notes)}</div>` : ""}${photos ? `<div>${photos}</div>` : ""}`);
}

export function payoutReceiptHtml(p: any) {
  return shell(p.receipt_number, `<div class="top"><div><h1>PAYOUT RECEIPT</h1><div class="muted">${esc(p.receipt_number)}</div></div><img class="logo" src="${LOGO_URL}"/></div>
<div class="grid"><div style="flex:1"><b>Paid to</b><br/>${esc(p.owner_name)}<br/>${esc(p.property_name)}</div>
<div style="flex:1"><b>Paid on:</b> ${fmtDate(p.paid_on)}<br/><b>Method:</b> ${esc(p.method)}<br/>${p.reference ? `<b>Reference:</b> ${esc(p.reference)}<br/>` : ""}<b>Period:</b> ${monthLabel(p.month)}</div></div>
<div class="box"><div class="muted">Amount paid</div><div class="big">${inr(p.amount)}</div></div>
<h3>How the payout is calculated</h3><table><tr><th>Statement summary</th><th class="r">Amount</th></tr>${calculationRows(p)}${amountRow('Amount paid', p.amount, false, true)}</table>
${supportingRows(p)}
${p.notes ? `<div class="box">${esc(p.notes)}</div>` : ""}`);
}

export async function sharePdf(html: string) {
  if (Platform.OS === "web") {
    await Print.printAsync({ html });
    return;
  }
  const { uri } = await Print.printToFileAsync({ html });
  if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(uri, { mimeType: "application/pdf", UTI: "com.adobe.pdf", dialogTitle: "Share PDF" });
}
