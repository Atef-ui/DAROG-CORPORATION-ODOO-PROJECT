import base64
from datetime import date

from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open

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
