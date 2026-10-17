# Darog Corporation (Odoo 18)

Export orders for garment accessories, and the full back-to-back L/C document set printed from each order.

## Layout

| Path | What it does |
| --- | --- |
| `models/darog_order.py` | Orders: parties, L/C dates, totals, amount in words, profit and invoice numbering. |
| `models/darog_measurement.py` | Order lines (item, size, quantity, price). |
| `models/darog_item.py` | Items. The line type (standard / poly bag / gum tape) is guessed from the name and can be edited; it decides which size fields an order line shows and how totals count it. |
| `models/darog_recipient.py` | Recipients (the L/C openers), their registration numbers, banks and starting invoice number. |
| `models/darog_company.py` | Your company: HS code and banner for the Certificate of Origin, cost exchange rate. |
| `models/darog_bank.py`, `darog_booking.py`, `darog_buyer.py`, `darog_profit.py` | Supporting records. |
| `wizard/darog_send_documents.py` | **Send by Email** window: emails an order's PDF documents to any address. |
| `views/` | Screens and menus. |
| `reports/darog_reports*.xml` | Paper format and the Print menu entries. |
| `reports/darog_templates*.xml` | The printed documents, one file each. |
| `reports/darog_pad.xml`, `models/ir_actions_report.py` | Prints the company pad behind the documents (see below). |
| `tests/` | Run with `--test-enable --test-tags=/DAROG`. |

## Invoice numbers

Numbers run per recipient and per year of the proforma invoice date.
A recipient's first year continues from its **Starting Invoice No**; every new year restarts at 1.
New orders get the next number automatically. **Renumber All Invoices** on the order form rebuilds every number from scratch.

## Printing

Documents open in a new browser tab (`static/src/js/open_pdf_in_tab.js`); if the browser blocks the tab, Odoo downloads the PDF instead.
If printing hangs, wkhtmltopdf can't reach the server at `web.base.url`. Set the system parameter
`report.url` to an address the server itself can reach, e.g. `http://127.0.0.1:8069`.

## Pad (letterhead)

Proforma Invoice, Commercial Invoice, Delivery Challan and Packing List are printed on the
company pad, `static/src/img/Pad.pdf`: it is placed behind every page after the PDF is made, so printing and
emailing both get it. Bill of Exchange, Certificate of Origin and Transportation stay plain.

The paper format **DAROG Pad** keeps the text clear of the pad on every page: 45 mm top margin (the pad's
header ends at 40.6 mm) and 23 mm bottom margin (its footer starts at 279.2 mm).

**One page.** Proforma Invoice, Commercial Invoice, Delivery Challan and Packing List always fit on one page.
If an order is too long, the document is made again, shrunk evenly (text and spacing together), at the
largest size that fits — a 40-line order prints at about 75 %, a 100-line order at about 45 %. Orders that
already fit are made once, at full size. The smallest size is 35 % (`MIN_SCALE` in
`models/ir_actions_report.py`); anything longer than that continues on a second page.

To change the pad, replace `Pad.pdf` (its crop box is scaled to cover the A4 page) and restart Odoo. If the new pad's
header or footer is taller, raise the margins in `reports/darog_pad.xml`.
Printing on pre-printed pad paper? The PDF already contains the pad, so use plain paper.

## Sending documents by email

**Send by Email** on an order opens a window to email its PDFs to any address (several allowed, separated by commas, plus Cc).
To is pre-filled from the recipient's **Email**; tick which documents to attach. Each PDF is the same as the printed one,
named like `Commercial Invoice - DC-CI-2026-006.pdf`.

Mail goes out through the first server in **Configuration > Outgoing Email Server** (admins only).
For Gmail: host `smtp.gmail.com`, port 465, SSL/TLS, username = the Gmail address, password = a 16-letter
App Password from https://myaccount.google.com/apppasswords (2-Step Verification must be on). Use **Test Connection** to check it.

## Upgrading an existing database

Model and field names are unchanged, so existing data carries over. Restart Odoo, then upgrade the module:

```
./odoo-bin -c <your config> -d <database> -u DAROG --stop-after-init
```
