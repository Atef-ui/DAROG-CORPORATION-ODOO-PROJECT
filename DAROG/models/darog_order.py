from collections import defaultdict
from datetime import date, timedelta

from odoo import api, fields, models

from .darog_company import DEFAULT_EXCHANGE_RATE

LC_TO_CHALLAN_DAYS = 15


class DarogOrder(models.Model):
    _name = "darog.order"
    _description = "Export Order"
    _order = "invoice_date desc, id desc"
    _rec_names_search = ["reciepent_id.name", "lc_no", "export_lc_no"]

    # Parties
    company_id = fields.Many2one(
        "darog.company",
        string="Company",
        default=lambda self: self.env["darog.company"].search([], limit=1),
    )
    reciepent_id = fields.Many2one("darog.reciepent", string="Recipient", index=True)
    buyer_id = fields.Many2one("darog.buyer", string="Buyer")
    bank_ids = fields.Many2many(
        "darog.bank",
        string="Banks",
        help="Banks linked to this order.",
    )
    issuing_bank_id = fields.Many2one("darog.bank", compute="_compute_issuing_bank_id", string="L/C Issuing Bank")

    # Status & numbering
    order_status = fields.Selection(
        [("new", "New"), ("in_progress", "In Progress"), ("delivered", "Delivered"), ("canceled", "Canceled")],
        string="Status",
        default="new",
    )
    invoice_no = fields.Integer(string="Invoice No", copy=False)
    pi_number = fields.Char(string="Proforma Invoice No", compute="_compute_document_numbers")
    ci_number = fields.Char(string="Commercial Invoice No", compute="_compute_document_numbers")

    # L/C details & dates
    lc_no = fields.Char(string="L/C No")
    export_lc_no = fields.Char(string="Export L/C No")
    invoice_date = fields.Date(string="Proforma Invoice Date", default=fields.Date.context_today)
    incoming_date = fields.Date(string="L/C Issuing Date")
    export_date = fields.Date(string="Export L/C Date")
    delivery_challan_date = fields.Date(
        compute="_compute_delivery_challan_date",
        store=True,
        string="Delivery Challan Date",
        help=f"L/C issuing date + {LC_TO_CHALLAN_DAYS} days.",
    )
    delivery_date = fields.Date(
        compute="_compute_delivery_date",
        store=True,
        string="Delivery Date",
        help="One day before the delivery challan date.",
    )
    payment_within = fields.Integer(string="Payment Within (Days)")

    # Goods
    items_id = fields.Many2many("darog.item", string="Items")
    measurement_ids = fields.One2many("darog.measurement", "orders_id", string="Order Lines")
    booking_type = fields.Selection(
        [("po", "P.O. NO."), ("styling", "STYLING NO."), ("booking", "BOOKING NO.")],
        default="booking",
    )
    booking_ids = fields.One2many("darog.booking", "order_id", string="Bookings")
    net_weight = fields.Float(string="Net Weight (KG)", digits=(16, 2))
    gross_weight = fields.Float(string="Gross Weight (KG)", digits=(16, 2))
    goods_weight = fields.Integer(string="Goods Weight (KG)", help="Only used when net and gross weight are empty.")

    # Totals
    total_amount = fields.Float(compute="_compute_total_amount", store=True, digits=(16, 2), string="Total (USD)")
    total_quantity = fields.Float(compute="_compute_totals", digits=(16, 2), string="Total Dozens")
    total_roll = fields.Float(compute="_compute_totals", digits=(16, 2), string="Total Gum Tape")
    gumtape_yards = fields.Boolean(compute="_compute_totals", string="Gum Tape in Yards")
    amount_in_words = fields.Char(compute="_compute_amount_in_words")
    # Stored so the Profit screen can group and total them.
    total_cost = fields.Float(compute="_compute_profit", store=True, digits=(16, 2), string="Total Cost (USD)")
    profit = fields.Float(compute="_compute_profit", store=True, digits=(16, 2), string="Profit (USD)")

    # Which recipient numbers to print on documents
    tin_no_needed = fields.Boolean(string="Print TIN No")
    bin_no_needed = fields.Boolean(string="Print BIN No")
    irc_no_needed = fields.Boolean(string="Print IRC No")
    erc_no_needed = fields.Boolean(string="Print ERC No")
    bond_reg_no_needed = fields.Boolean(string="Print Bond Reg No")
    bb_no_needed = fields.Boolean(string="Print Bank BIN No")
    ref_no_needed = fields.Boolean(string="Print Reference No")
    ref_no = fields.Char(string="Reference No")

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("invoice_no", "invoice_date", "reciepent_id.name")
    def _compute_display_name(self):
        for order in self:
            parts = [order.pi_number if order.invoice_no else False, order.reciepent_id.name]
            order.display_name = " · ".join(filter(None, parts)) or "New Order"

    @api.depends("invoice_no", "invoice_date")
    def _compute_document_numbers(self):
        for order in self:
            year = order.invoice_date.year if order.invoice_date else ""
            number = f"{order.invoice_no:03d}"
            order.pi_number = f"DC/{year}/{number}"
            order.ci_number = f"DC/CI/{year}/{number}"

    @api.depends("bank_ids", "reciepent_id.bank_id")
    def _compute_issuing_bank_id(self):
        for order in self:
            banks = order.reciepent_id.bank_id
            if len(banks) != 1 and order.bank_ids:
                order.issuing_bank_id = order.bank_ids[:1]
            else:
                order.issuing_bank_id = banks[:1]

    @api.depends("incoming_date")
    def _compute_delivery_challan_date(self):
        for order in self:
            order.delivery_challan_date = order.incoming_date and order.incoming_date + timedelta(days=LC_TO_CHALLAN_DAYS)

    @api.depends("delivery_challan_date")
    def _compute_delivery_date(self):
        for order in self:
            order.delivery_date = order.delivery_challan_date and order.delivery_challan_date - timedelta(days=1)

    @api.depends("measurement_ids.total_price")
    def _compute_total_amount(self):
        for order in self:
            order.total_amount = sum(order.measurement_ids.mapped("total_price"))

    @api.depends("measurement_ids.quantity", "measurement_ids.yards", "measurement_ids.items_id.print_style")
    def _compute_totals(self):
        for order in self:
            dozens = rolls = 0.0
            in_yards = False
            for line in order.measurement_ids:
                if line.print_style == "gumtape":
                    rolls += line._total_yards() if line.yards > 0 else line.quantity
                    in_yards = in_yards or line.yards > 0
                else:
                    dozens += line.quantity
            order.total_quantity = dozens
            order.total_roll = rolls
            order.gumtape_yards = in_yards

    @api.depends("total_amount", "company_id.currency_id")
    def _compute_amount_in_words(self):
        # Wording (including its spacing) matches what the documents have always printed.
        for order in self:
            currency = order.company_id.currency_id or self.env.company.currency_id
            amount = order.total_amount or 0.0
            if currency.name != "USD":
                order.amount_in_words = f"{currency.amount_to_text(amount)} ONLY"
                continue
            whole, cents = divmod(round(amount * 100), 100)
            whole_text = currency.amount_to_text(whole).replace(",", "")
            if cents:
                cents_text = currency.amount_to_text(cents).replace(",", "")
                for word in ("Dollars", "Dollar"):
                    whole_text = whole_text.replace(word, "")
                    cents_text = cents_text.replace(word, "")
                whole_text = whole_text.replace("And", "")
                order.amount_in_words = f"{whole_text} & CENTS {cents_text} ONLY"
            else:
                order.amount_in_words = f"{whole_text} ONLY"

    @api.depends("total_amount", "measurement_ids.quantity", "measurement_ids.cost_price",
                 "company_id.exchange_rate")
    def _compute_profit(self):
        for order in self:
            rate = order.company_id.exchange_rate or DEFAULT_EXCHANGE_RATE
            cost = sum(line.quantity * line.cost_price for line in order.measurement_ids)
            order.total_cost = cost / rate
            order.profit = order.total_amount - cost / rate

    @api.onchange("measurement_ids")
    def _onchange_measurement_ids(self):
        self._add_missing_items()

    # ------------------------------------------------------------------
    # Invoice numbering
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        last_numbers = {}
        for vals in vals_list:
            if vals.get("reciepent_id") and not vals.get("invoice_no"):
                invoice_date = fields.Date.to_date(vals.get("invoice_date")) or fields.Date.context_today(self)
                key = (vals["reciepent_id"], invoice_date.year)
                if key not in last_numbers:
                    last_numbers[key] = self._last_invoice_no(*key)
                last_numbers[key] += 1
                vals["invoice_no"] = last_numbers[key]
        orders = super().create(vals_list)
        orders._ensure_profit_records()
        return orders

    @api.model
    def _last_invoice_no(self, recipient_id, year):
        """Highest number used for this recipient and year.

        A recipient's first year continues from its starting invoice number;
        every following year restarts at 0.
        """
        recipient = self.env["darog.reciepent"].browse(recipient_id)
        year_start = date(year, 1, 1)
        same_year = self.search([
            ("reciepent_id", "=", recipient_id),
            ("invoice_date", ">=", year_start),
            ("invoice_date", "<", date(year + 1, 1, 1)),
        ], order="invoice_no desc", limit=1)
        if same_year:
            return same_year.invoice_no
        has_earlier_year = self.search_count([
            ("reciepent_id", "=", recipient_id),
            ("invoice_date", "<", year_start),
        ], limit=1)
        return 0 if has_earlier_year else recipient.default_invoice_no

    def action_backfill_invoice_numbers(self):
        """Renumber every dated order, per recipient and year, oldest first."""
        orders = self.search([("reciepent_id", "!=", False), ("invoice_date", "!=", False)],
                             order="invoice_date asc, id asc")
        by_recipient = defaultdict(lambda: defaultdict(list))
        for order in orders:
            by_recipient[order.reciepent_id][order.invoice_date.year].append(order)

        for recipient, years in by_recipient.items():
            for index, year in enumerate(sorted(years)):
                counter = recipient.default_invoice_no if index == 0 else 0
                for order in years[year]:
                    counter += 1
                    if order.invoice_no != counter:
                        order.invoice_no = counter
            recipient.invoice_year = max(years)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": f"Invoice numbers reassigned for {len(orders)} orders.",
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def action_send_documents(self):
        """Open the Send by Email window for this order."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("DAROG.darog_send_documents_action")
        action["context"] = {"default_order_id": self.id}
        return action

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _ensure_profit_records(self):
        """Every order gets one row in Profit. Called on create and on module install/upgrade."""
        orders = self or self.search([])
        existing = self.env["darog.profit"].search([("order_id", "in", orders.ids)]).order_id
        missing = orders - existing
        if missing:
            self.env["darog.profit"].create([{"order_id": order.id} for order in missing])

    def _add_missing_items(self):
        """Every item used on an order line must be in the order's item list, or it won't print."""
        for order in self:
            missing = order.measurement_ids.items_id - order.items_id
            if missing:
                order.items_id |= missing
