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
| `views/` | Screens and menus. |
| `reports/darog_reports*.xml` | Paper format and the Print menu entries. |
| `reports/darog_templates*.xml` | The printed documents, one file each, tuned to the pre-printed pad. |
| `tests/` | Run with `--test-enable --test-tags=/DAROG`. |

## Invoice numbers

Numbers run per recipient and per year of the proforma invoice date.
A recipient's first year continues from its **Starting Invoice No**; every new year restarts at 1.
New orders get the next number automatically. **Renumber All Invoices** on the order form rebuilds every number from scratch.

## Printing

Documents open in a new browser tab (`static/src/js/open_pdf_in_tab.js`); if the browser blocks the tab, Odoo downloads the PDF instead.
If printing hangs, wkhtmltopdf can't reach the server at `web.base.url`. Set the system parameter
`report.url` to an address the server itself can reach, e.g. `http://127.0.0.1:8069`.

## Upgrading an existing database

Model and field names are unchanged, so existing data carries over. Restart Odoo, then upgrade the module:

```
./odoo-bin -c <your config> -d <database> -u DAROG --stop-after-init
```
