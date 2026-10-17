import base64
import io
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open
from odoo.tools.pdf import PdfFileReader

REPORTS = [
    "DAROG.report_darog",
    "DAROG.report_darog_com",
    "DAROG.report_darog_bill",
    "DAROG.report_darog_delivery",
    "DAROG.report_darog_packing",
    "DAROG.report_darog_origin",
    "DAROG.report_darog_transport",
]


@tagged("post_install", "-at_install")
class TestDarog(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with file_open("DAROG/static/src/img/image.png", "rb") as image:
            certificate = base64.b64encode(image.read())
        cls.company = cls.env["darog.company"].create({"name": "Darog Corporation", "certificate": certificate})
        cls.recipient = cls.env["darog.reciepent"].create({
            "name": "ABC Garments Ltd.",
            "address": "Gazipur,Dhaka",
            "tin_no": "TIN-1",
            "bin_no": "BIN-2",
            "default_invoice_no": 4,
        })
        cls.bank = cls.env["darog.bank"].create({"name": "Sonali Bank", "bank_bin": "BB-9", "reciepent_id": cls.recipient.id})
        Item = cls.env["darog.item"]
        cls.poly = Item.create({"name": "PRE-PACK: MILKY WHITE", "price_per_unit": 30})
        cls.tissue = Item.create({"name": "TISSUE PAPER", "price_per_unit": 12})
        cls.board = Item.create({"name": "CARD BOARD: W/B-350 GSM.", "price_per_unit": 20})
        cls.gum = Item.create({"name": "PAPER GUMTAPE", "description": "BROWN GUMTAPE", "price_per_unit": 50})

    def _order(self, **vals):
        return self.env["darog.order"].create({
            "reciepent_id": self.recipient.id,
            "company_id": self.company.id,
            **vals,
        })

    def test_item_print_style_guessed_from_name(self):
        self.assertEqual(self.poly.print_style, "poly")
        self.assertEqual(self.gum.print_style, "gumtape")
        self.assertEqual(self.tissue.print_style, "standard")

    def test_invoice_numbering(self):
        first = self._order(invoice_date=date(2026, 1, 5))
        second = self._order(invoice_date=date(2026, 2, 5))
        self.assertEqual(first.invoice_no, 5, "first year continues from the starting number")
        self.assertEqual(second.invoice_no, 6)
        self.assertEqual(second.pi_number, "DC/2026/006")
        self.assertEqual(second.ci_number, "DC/CI/2026/006")
        next_year = self._order(invoice_date=date(2027, 1, 2))
        self.assertEqual(next_year.invoice_no, 1, "numbering restarts every new year")

        batch = self.env["darog.order"].create([
            {"reciepent_id": self.recipient.id, "invoice_date": date(2026, 3, 1)},
            {"reciepent_id": self.recipient.id, "invoice_date": date(2026, 3, 2)},
        ])
        self.assertEqual(batch.mapped("invoice_no"), [7, 8])

        (first | second | next_year | batch).write({"invoice_no": 99})
        self.env["darog.order"].action_backfill_invoice_numbers()
        self.assertEqual([first.invoice_no, second.invoice_no, *batch.mapped("invoice_no")], [5, 6, 7, 8])
        self.assertEqual(next_year.invoice_no, 1)

    def test_totals_and_words(self):
        order = self._order(measurement_ids=[
            (0, 0, {"items_id": self.poly.id, "quantity": 150, "per_unit_price": 0.35}),
            (0, 0, {"items_id": self.tissue.id, "quantity": 3, "per_unit_price": 0.1}),
            (0, 0, {"items_id": self.gum.id, "quantity": 10, "yards": 33, "per_unit_price": 1.25}),
        ])
        self.assertAlmostEqual(order.total_amount, 52.5 + 0.3 + 12.5)
        self.assertEqual(order.total_quantity, 153)
        self.assertEqual(order.total_roll, 330)
        self.assertTrue(order.gumtape_yards)
        self.assertIn("& CENTS", order.amount_in_words)
        self.assertTrue(order.amount_in_words.endswith("ONLY"))
        self.assertEqual(order.items_id, self.poly | self.tissue | self.gum, "line items are added to the order")
        # cost 150*30 + 3*12 + 10*50 = 5036 local currency / 120
        self.assertAlmostEqual(order.total_cost, 5036 / 120, places=2)
        self.assertAlmostEqual(order.profit, order.total_amount - 5036 / 120, places=2)

    def test_every_order_appears_in_profit(self):
        order = self._order(order_status="delivered", measurement_ids=[
            (0, 0, {"items_id": self.poly.id, "quantity": 10, "per_unit_price": 10}),
        ])
        profit = self.env["darog.profit"].search([("order_id", "=", order.id)])
        self.assertEqual(len(profit), 1, "new orders get a Profit row automatically")
        self.assertEqual(profit.reciepent, "ABC Garments Ltd.")
        self.assertEqual(profit.order_status, "delivered")
        self.assertAlmostEqual(profit.profit, order.profit)
        # Orders without a row (e.g. created before this existed) are filled in on upgrade.
        profit.unlink()
        self.env["darog.order"]._ensure_profit_records()
        self.assertEqual(self.env["darog.profit"].search_count([("order_id", "=", order.id)]), 1)
        self.env["darog.order"]._ensure_profit_records()
        self.assertEqual(self.env["darog.profit"].search_count([("order_id", "=", order.id)]), 1, "never duplicated")

    def test_prices_and_costs_are_per_order(self):
        line = {"items_id": self.poly.id, "quantity": 100}
        first = self._order(measurement_ids=[(0, 0, {**line, "per_unit_price": 0.30})])
        second = self._order(measurement_ids=[(0, 0, {**line, "per_unit_price": 0.45})])
        self.assertAlmostEqual(first.total_amount, 30.0)
        self.assertAlmostEqual(second.total_amount, 45.0, msg="same item, different price per order")
        self.assertEqual(first.measurement_ids.cost_price, 30, "cost is filled in from the item")

        first_profit = first.profit
        self.poly.price_per_unit = 99
        self.assertAlmostEqual(first.profit, first_profit, msg="changing the item cost leaves past orders alone")
        third = self._order(measurement_ids=[(0, 0, {**line, "per_unit_price": 0.45})])
        self.assertEqual(third.measurement_ids.cost_price, 99, "new lines use the new cost")

        second.measurement_ids.cost_price = 12
        self.assertAlmostEqual(second.total_cost, 100 * 12 / 120, msg="each order can have its own cost")

    def test_whole_dollar_words(self):
        order = self._order(measurement_ids=[(0, 0, {"items_id": self.poly.id, "quantity": 10, "per_unit_price": 10})])
        self.assertNotIn("CENTS", order.amount_in_words)
        self.assertTrue(order.amount_in_words.endswith("ONLY"))

    def test_dates(self):
        order = self._order(incoming_date=date(2026, 3, 10))
        self.assertEqual(order.delivery_challan_date, date(2026, 3, 25))
        self.assertEqual(order.delivery_date, date(2026, 3, 24))
        order.incoming_date = False
        self.assertFalse(order.delivery_challan_date)
        self.assertFalse(order.delivery_date)

    def test_issuing_bank(self):
        order = self._order()
        self.assertEqual(order.issuing_bank_id, self.bank)
        second = self.env["darog.bank"].create({"name": "Uttara Bank", "reciepent_id": self.recipient.id})
        order.bank_ids = second
        self.assertEqual(order.issuing_bank_id, second, "with several recipient banks the order's bank is used")

    def test_render_reports(self):
        full = self._order(
            invoice_date=date(2026, 3, 2), incoming_date=date(2026, 3, 10), export_date=date(2026, 2, 20),
            lc_no="LC-1", export_lc_no="EXP-1", tin_no_needed=True,
            items_id=[(6, 0, [self.poly.id, self.gum.id])],
            booking_ids=[(0, 0, {"booking_no": "BK-1"})],
            measurement_ids=[
                (0, 0, {"items_id": self.poly.id, "length": 12, "width": 10, "adhesive": 2, "measure": "inch",
                        "quantity": 150, "per_unit_price": 0.35}),
                (0, 0, {"items_id": self.gum.id, "quantity": 10, "per_unit_price": 1.25}),
            ],
        )
        Report = self.env["ir.actions.report"]
        for report in REPORTS:
            html = Report._render_qweb_html(report, full.ids)[0].decode()
            self.assertTrue(html, report)
        html = Report._render_qweb_html("DAROG.report_darog", full.ids)[0].decode()
        self.assertIn("DC/2026/005", html)
        self.assertIn("02.03.2026", html)
        self.assertIn("$0.35", html)
        for report in ("DAROG.report_darog", "DAROG.report_darog_com", "DAROG.report_darog_delivery", "DAROG.report_darog_packing"):
            html = Report._render_qweb_html(report, full.ids)[0].decode()
            self.assertIn("10 INCH", html, f"{report}: size units print in capitals")
            self.assertNotIn(" inch", html, report)

    def test_send_documents_by_email(self):
        self.recipient.email = "buyer@example.com"
        order = self._order(invoice_date=date(2026, 3, 2), incoming_date=date(2026, 3, 10),
                            export_date=date(2026, 2, 20), lc_no="LC-9", measurement_ids=[
            (0, 0, {"items_id": self.poly.id, "quantity": 10, "per_unit_price": 2}),
        ])
        Wizard = self.env["darog.send.documents"].with_context(default_order_id=order.id)

        wizard = Wizard.create({})
        self.assertEqual(wizard.email_to, "buyer@example.com", "To is filled from the recipient")
        self.assertIn("DC/CI/2026/005", wizard.subject)
        self.assertIn("Darog Corporation", wizard.body)

        wizard.write({"attach_bill": False, "attach_transport": False})
        names = [name for name, _content, _mime in wizard._attachments()]
        self.assertEqual(names, [
            "Proforma Invoice - DC-CI-2026-005.pdf",
            "Commercial Invoice - DC-CI-2026-005.pdf",
            "Delivery Challan - DC-CI-2026-005.pdf",
            "Packing List - DC-CI-2026-005.pdf",
            "Certificate of Origin - DC-CI-2026-005.pdf",
        ])

        self.env["ir.mail_server"].search([]).active = False  # start with no server
        with self.assertRaisesRegex(UserError, "outgoing email server"):
            wizard.action_send()
        self.env["ir.mail_server"].create({
            "name": "Gmail", "smtp_host": "smtp.gmail.com", "smtp_port": 465, "smtp_encryption": "ssl",
            "smtp_user": "sender@gmail.com", "smtp_pass": "x",
        })
        server = self.env["ir.mail_server"].search([], limit=1)
        self.assertEqual(wizard._sender(server), '"Darog Corporation" <sender@gmail.com>', "sender shows the company name")
        self.company.email_sender_name = "Darog Accounts"
        self.assertEqual(wizard._sender(server), '"Darog Accounts" <sender@gmail.com>')
        wizard.email_to = "anyone@example.org, second@example.net"
        result = wizard.action_send()
        self.assertIn("Sent 5 document(s) to anyone@example.org, second@example.net", result["params"]["message"])

        with self.assertRaisesRegex(UserError, "not a valid email"):
            Wizard.create({"email_to": "not-an-email"}).action_send()
        with self.assertRaisesRegex(UserError, "at least one document"):
            Wizard.create({field: False for field in (
                "attach_proforma", "attach_commercial", "attach_bill", "attach_delivery",
                "attach_packing", "attach_origin", "attach_transport")}).action_send()

        undated = self._order(measurement_ids=[(0, 0, {"items_id": self.poly.id, "quantity": 1})])
        result = Wizard.with_context(default_order_id=undated.id).create({"email_to": "a@example.com"}).action_send()
        self.assertIn("Sent 7 document(s)", result["params"]["message"], "orders with empty dates can be sent")

        action = order.action_send_documents()
        self.assertEqual(action["res_model"], "darog.send.documents")
        self.assertEqual(action["context"]["default_order_id"], order.id)

    def test_pad_background(self):
        pad_format = self.env.ref("DAROG.paperformat_darog_pad")
        for xmlid in ("action_report_darog", "action_report_darog_com",
                      "action_report_darog_delivery", "action_report_darog_packing"):
            self.assertEqual(self.env.ref(f"DAROG.{xmlid}").paperformat_id, pad_format, xmlid)
        for xmlid in ("action_report_darog_bill", "action_report_darog_origin", "action_report_darog_transport"):
            self.assertNotEqual(self.env.ref(f"DAROG.{xmlid}").paperformat_id, pad_format, f"{xmlid} stays plain")
        self.assertGreaterEqual(pad_format.margin_top, 42, "text starts below the pad header (41.5 mm)")
        self.assertGreaterEqual(pad_format.margin_bottom, 19, "text stops above the pad footer (278.4 mm)")

        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        plain = io.BytesIO()
        pdf = canvas.Canvas(plain, pagesize=A4)
        for text in ("PAGE ONE", "PAGE TWO"):
            pdf.drawString(100, 400, text)
            pdf.showPage()
        pdf.save()
        padded = self.env["ir.actions.report"]._darog_add_pad(plain.getvalue())
        pages = PdfFileReader(io.BytesIO(padded)).pages
        self.assertEqual(len(pages), 2, "every page is kept")
        for page in pages:
            box = [float(value) for value in (page.mediabox if hasattr(page, "mediabox") else page.mediaBox)]
            self.assertAlmostEqual(box[2] - box[0], A4[0], places=0)
            self.assertAlmostEqual(box[3] - box[1], A4[1], places=0)
        self.assertGreater(len(padded), len(plain.getvalue()) + 50_000, "the pad is drawn on each page")

    def test_big_orders_fit_on_one_page(self):
        import math
        from unittest.mock import patch

        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        from odoo.addons.DAROG.models.ir_actions_report import FIT_STEPS, MIN_SCALE, _page_count

        def pdf_with(pages):
            buffer = io.BytesIO()
            pdf = canvas.Canvas(buffer, pagesize=A4)
            for _page in range(pages):
                pdf.showPage()
            pdf.save()
            return buffer.getvalue()

        Report = self.env["ir.actions.report"]
        content = {"pages": 2.6}  # how many pages the order takes at full size
        scales = []

        def render_at(_self, report_ref, res_id, data, scale):
            scales.append(scale)
            return pdf_with(max(1, math.ceil(content["pages"] * scale - 1e-9)))

        with patch.object(type(Report), "_darog_render_at", render_at):
            result = Report._darog_render_one_page("DAROG.report_darog_com", 1, None)
            self.assertEqual(_page_count(result), 1, "a big order ends up on one page")
            best = max(s for s in scales if content["pages"] * s <= 1)
            self.assertGreater(best, 1 / 2.6 - 0.04, "shrunk only as much as needed")
            self.assertLessEqual(len(scales), FIT_STEPS + 2, "a few tries only")

            scales.clear()
            content["pages"] = 0.8
            Report._darog_render_one_page("DAROG.report_darog_com", 1, None)
            self.assertEqual(scales, [1.0], "an order that fits is made once, at full size")

            scales.clear()
            content["pages"] = 10
            Report._darog_render_one_page("DAROG.report_darog_com", 1, None)
            self.assertEqual(min(scales), MIN_SCALE, "never shrinks below the minimum")

    def test_no_line_under_the_header(self):
        order = self._order(invoice_date=date(2026, 3, 2), incoming_date=date(2026, 3, 10),
                            export_date=date(2026, 2, 20))
        for report in ("DAROG.report_darog", "DAROG.report_darog_com", "DAROG.report_darog_delivery",
                       "DAROG.report_darog_packing"):
            html = self.env["ir.actions.report"]._render_qweb_html(report, order.ids)[0].decode()
            logo_css = html[html.index(".logo{"):html.index("}", html.index(".logo{"))]
            self.assertNotIn("2px solid black", logo_css, report)

    def test_documents_print_with_empty_dates(self):
        # Only the proforma invoice date is set: L/C, export and delivery dates are empty.
        order = self._order(invoice_date=date(2026, 3, 2), measurement_ids=[
            (0, 0, {"items_id": self.poly.id, "quantity": 10, "per_unit_price": 2}),
        ])
        self.assertFalse(order.incoming_date or order.export_date or order.delivery_date)
        Report = self.env["ir.actions.report"]
        for report in REPORTS:
            html = Report._render_qweb_html(report, order.ids)[0].decode()
            self.assertTrue(html, report)
        html = Report._render_qweb_html("DAROG.report_darog_com", order.ids)[0].decode()
        self.assertIn("DC/CI/2026/005", html, "without an L/C date the number uses the invoice year")
        nothing = self._order(invoice_date=False)
        for report in REPORTS:
            self.assertTrue(Report._render_qweb_html(report, nothing.ids)[0], f"{report} with no dates at all")

    def test_profit_grouping_and_totals(self):
        other = self.env["darog.reciepent"].create({"name": "XYZ Fashions"})
        line = {"items_id": self.poly.id, "quantity": 100, "cost_price": 24}  # cost 100 * 24 / 120 = $20
        a = self._order(measurement_ids=[(0, 0, {**line, "per_unit_price": 0.5})], order_status="delivered")
        b = self._order(measurement_ids=[(0, 0, {**line, "per_unit_price": 0.3})])
        c = self._order(reciepent_id=other.id, measurement_ids=[(0, 0, {**line, "per_unit_price": 0.1})])
        Profit = self.env["darog.profit"]
        domain = [("order_id", "in", (a | b | c).ids)]

        groups = {g["reciepent_id"][1]: g for g in Profit.read_group(
            domain, ["total_amount:sum", "total_cost:sum", "profit:sum"], ["reciepent_id"])}
        self.assertAlmostEqual(groups["ABC Garments Ltd."]["total_amount"], 80)
        self.assertAlmostEqual(groups["ABC Garments Ltd."]["total_cost"], 40)
        self.assertAlmostEqual(groups["ABC Garments Ltd."]["profit"], 40)
        self.assertAlmostEqual(groups["XYZ Fashions"]["profit"], -10, msg="losses count too")

        row = Profit.search([("order_id", "=", a.id)])
        self.assertAlmostEqual(row.margin, 0.6, msg="profit 30 on a total of 50")
        a.measurement_ids.per_unit_price = 1.0
        self.assertAlmostEqual(row.profit, 80, msg="the profit row follows price changes")
        b.order_status = "canceled"
        self.assertEqual(Profit.search_count(domain + [("order_status", "!=", "canceled")]), 2)

