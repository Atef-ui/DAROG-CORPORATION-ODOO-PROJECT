from odoo import api,models,fields
from datetime import datetime,timedelta
class company(models.Model):
    _name="darog.company"
    _description="Company Model"
    name=fields.Char(required=True)
    logo=fields.Binary()
    item_ids=fields.Many2many("darog.item",string="Items")
    hs_code=fields.Char(string="HS Code")
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id
    )
    certificate=fields.Binary(string="Certificate")
    address=fields.Text()
class order(models.Model):
    _name="darog.order"
    _description="Order Model"
    #company_id = fields.Many2one(
    #    "darog.company",
    #    string="Company",
    #    default=lambda self: self.env["darog.company"].search([], limit=1)
    #)
    reciepent_id=fields.Many2one("darog.reciepent",string="Reciepent")
    invoice_date=fields.Date(string="Proforma Invoice Date")
    incoming_date=fields.Date(string="L/C ISSUING Date")
    delivery_challan_date=fields.Date(compute="_compute_delivery_challan_date",store=True,string="Delivery Challan Date")
    delivery_date=fields.Date(compute="_compute_delivery_date",store=True,string="Delivery Date")
    export_date=fields.Date(string="Export L/C Date")
    company_id=fields.Many2one("darog.company",string="Company",default=lambda self: self.env['darog.company'].search([],limit=1))
    items_id=fields.Many2many("darog.item",string="Items")
    booking_ids=fields.One2many("darog.booking","order_id",string="Booking")
    net_weight=fields.Float(string="Net Weight",digits=(16,2))
    gross_weight=fields.Float(string="Gross Weight",digits=(16,2))
    goods_weight=fields.Integer(string="Goods Weight(IF NO GROSS AND NET WEIGHT)")
    order_status=fields.Selection([
        ('new','New'),
        ('in_progress','In Progress'),
        ('delivered','Delivered'),
        ('canceled','Canceled'),],default='new')
    booking_type=fields.Selection([
        ('po','P.O. NO.'),
        ('styling','STYLING NO.'),
        ('booking','BOOKING NO.'),],default='booking')
    total_amount=fields.Float(compute="net_total",digits=(16,2))
    measurement_ids=fields.One2many("darog.measurement","orders_id",string="Measurements")
    amount_in_words=fields.Char(compute="_compute_amount_in_words")
    lc_no=fields.Char(string="LC No")
    export_lc_no=fields.Char(string="Export LC No")
    bank_ids=fields.Many2many("darog.bank",string="Banks")
    total_quantity=fields.Float(compute="_compute_total_quantity",digits=(16,2))
    total_roll=fields.Float(compute="_compute_total_roll",digits=(16,2),default=0)
    invoice_no = fields.Integer(string="INVOICE NO:", readonly=False, copy=False)
    buyer_id=fields.Many2one("darog.buyer",string="Buyer")
    payment_within=fields.Integer(string="Payment Within (Days)")
    tin_no_needed=fields.Boolean(string="TIN No")
    bin_no_needed=fields.Boolean(string="BIN No")
    irc_no_needed=fields.Boolean(string="IRC No")
    erc_no_needed=fields.Boolean(string="ERC No")
    bond_reg_no_needed=fields.Boolean(string="Bond Reg No")
    bb_no_needed=fields.Boolean(string="BANK BIN No")
    @api.depends("incoming_date")
    def _compute_delivery_challan_date(self):
        for record in self:
            if record.incoming_date:
                record.delivery_challan_date = (record.incoming_date + timedelta(days=15))
    @api.depends("delivery_challan_date")
    def _compute_delivery_date(self):
        for record in self:
            if record.delivery_challan_date:
                record.delivery_date = (record.delivery_challan_date - timedelta(days=1))
    @api.model_create_multi
    def create(self, vals_list):
        counter = 0
        for vals in vals_list:
            if vals.get("reciepent_id"):

            # get year from incoming_date, fallback to current year
                year = (
                    fields.Date.from_string(vals["incoming_date"]).year
                    if vals.get("incoming_date")
                    else datetime.now().year
                )

                recipient = self.env["darog.reciepent"].browse(vals["reciepent_id"])

            # year changed → reset counter back to 0
                if recipient.invoice_year != year:
                    recipient.invoice_year = year
                    recipient.default_invoice_no = 0
                    counter = 0

            # increment counter by 1 and assign to invoice_no
                counter += 1
                vals["invoice_no"] = recipient.default_invoice_no + counter

        return super().create(vals_list)

    # ← ADD HERE, same indentation as create()
    def action_backfill_invoice_numbers(self):
        recipients = self.env["darog.reciepent"].search([])

        for recipient in recipients:

        # get all orders with a date, oldest first
            orders = self.search(
                [
                    ("reciepent_id", "=", recipient.id),
                    ("invoice_date", "!=", False),
                ],
                order="invoice_date asc, id asc"
            )

        # group orders by year
            orders_by_year = {}
            for order in orders:
                year = order.invoice_date.year
                if year not in orders_by_year:
                    orders_by_year[year] = []
                orders_by_year[year].append(order)

        # assign sequential numbers, reset counter for each year
            counter = 0
            heel = 0
            last_year = None
            for year in sorted(orders_by_year.keys()):
                if heel == 0: counter = recipient.default_invoice_no  # reset to default_invoice_no at start of 1st year
                else: counter = 0 #reset to 0 after every year except 1st one
                for order in orders_by_year[year]:
                    counter += 1
                    order.invoice_no = counter

                last_year = year
                heel+=1

        # sync recipient counter to match current state
            if last_year:
                recipient.invoice_year = last_year
    @api.depends("measurement_ids.quantity")
    def _compute_total_quantity(self):
        for record in self:
            total=0
            for measurement in record.measurement_ids:
                if measurement not in ['PAPER GUMTAPE']:
                    total+=measurement.quantity
            record.total_quantity=total
    @api.depends("measurement_ids.total_price")
    def net_total(self):
        for record in self:
            total=0
            for measurement in record.measurement_ids:
                total+=measurement.total_price
            record.total_amount=total
    @api.depends("total_amount", "company_id.currency_id")
    def _compute_amount_in_words(self):
        for record in self:
            currency = record.company_id.currency_id if record.company_id else self.env.company.currency_id
            amount = record.total_amount or 0.0

            whole = int(amount)
            cents = int(round((amount - whole) * 100))

            if currency.name == "USD":
                whole_text = currency.amount_to_text(whole)
                if cents:
                    cents_text = currency.amount_to_text(cents)
                    whole_text = currency.amount_to_text(whole).replace(",", "")
                    cents_text = currency.amount_to_text(cents).replace(",", "")
                    cents_text = cents_text.replace("Dollars","")
                    cents_text= cents_text.replace("Dollar","")
                    whole_text = whole_text.replace("Dollars","")
                    whole_text = whole_text.replace("Dollar","")
                    whole_text = whole_text.replace("And","")
                    record.amount_in_words = f"{whole_text} & CENTS {cents_text} ONLY"
                else:
                    whole_text = currency.amount_to_text(whole).replace(",", "")
                    record.amount_in_words = f"{whole_text} ONLY"
            else:
                record.amount_in_words = f"{currency.amount_to_text(amount)} ONLY"
    @api.depends("measurement_ids.quantity")
    def _compute_total_roll(self):
        for record in self:
            total=0
            for measurement in record.measurement_ids:
                if measurement.items_id.name in ['PAPER GUMTAPE']:
                    total+=measurement.quantity
            record.total_roll=total
class item(models.Model):
    _name="darog.item"
    _description="Item Model"
    name=fields.Char(required=True)
    order_ids=fields.Many2many("darog.order",string="Companies")
    description=fields.Char()
    measurement_ids=fields.One2many("darog.measurement","items_id",string="Measurements")
class booking(models.Model):
    _name="darog.booking"
    _description="Booking Model"
    booking_no=fields.Char(required=True)
    order_id=fields.Many2one("darog.order",string="Order")
class reciepent(models.Model):
    _name="darog.reciepent"
    _description="Reciepent Model"
    erc_no=fields.Char(string="ERC No")
    irc_no=fields.Char(string="IRC No")
    name=fields.Char(required=True)
    address=fields.Text()
    order_ids=fields.One2many("darog.order","reciepent_id",string="Orders")
    bin_no=fields.Char(string="BIN No")
    tin_no=fields.Char(string="TIN No")
    bank_id=fields.One2many("darog.bank","reciepent_id",string="Bank")
    default_invoice_no = fields.Integer(string="Default Invoice No", default=0)  # counter
    invoice_year = fields.Integer(default=lambda self: datetime.now().year)       # tracks current year
    bond_reg_no=fields.Char(string="Bond Reg No")
    bb_no=fields.Char(string="BB No")
class bank(models.Model):
    _name="darog.bank"
    _description="Bank Model"
    name=fields.Char(required=True)
    reciepent_id=fields.Many2one("darog.reciepent",string="Reciepent")
    address=fields.Text()
    order_ids=fields.Many2many("darog.order",string="Orders")
    bank_bin=fields.Char(string="Bank BIN")
class measurement(models.Model):
    _name="darog.measurement"
    _description="Measurement Model"
    items_id=fields.Many2one("darog.item",string="Item")
    orders_id=fields.Many2one("darog.order",string="Order")
    width=fields.Integer()
    length=fields.Integer()
    measure=fields.Char()
    quantity=fields.Float()
    quantity_unit=fields.Selection([
        ('dozon','DZN'),
        ('yards','YARDS'),
        ('roll','ROLL'),
    ])
    per_unit_price=fields.Float()
    adhesive=fields.Integer()
    total_price=fields.Float(compute="_compute_total_price",digits=(16,2))
    @api.onchange("items_id.name")
    def _onchange_measure(self):
        if self.items_id.name not in ['PAPER GUMTAPE']:
            self.measure='dozon'
    @api.depends("quantity","per_unit_price")
    def _compute_total_price(self):
        for record in self:
            record.total_price=record.quantity*record.per_unit_price
    @api.depends("items_id")
    def _compute_ids(self):
        for record in self:
            record.items_id.order_ids=record.orders_id
class buyer(models.Model):
    _name="darog.buyer"
    _description="Buyer Model"
    name=fields.Char(required=True)
    order_ids=fields.Many2one("darog.order",string="Orders")