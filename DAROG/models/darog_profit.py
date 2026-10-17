from odoo import api, fields, models


class DarogProfit(models.Model):
    """One row per order, for grouping and totalling profit (see views/darog_profit_views.xml)."""
    _name = "darog.profit"
    _description = "Order Profit"
    _order = "invoice_date desc, id desc"

    order_id = fields.Many2one("darog.order", string="Order", ondelete="cascade", index=True)

    # Grouping
    reciepent_id = fields.Many2one(related="order_id.reciepent_id", string="Recipient", store=True)
    reciepent = fields.Char(related="order_id.reciepent_id.name", string="Recipient Name", store=True)
    buyer_id = fields.Many2one(related="order_id.buyer_id", string="Buyer", store=True)
    company_id = fields.Many2one(related="order_id.company_id", string="Company", store=True)
    invoice_no = fields.Integer(related="order_id.invoice_no", string="Invoice No", store=True)
    invoice_date = fields.Date(related="order_id.invoice_date", string="Invoice Date", store=True)
    delivery_date = fields.Date(related="order_id.delivery_date", string="Delivery Date", store=True)
    order_status = fields.Selection(related="order_id.order_status", string="Status", store=True)

    # Money (USD), summed in groups and at the bottom of the list
    total_amount = fields.Float(related="order_id.total_amount", string="Total (USD)", store=True,
                                digits=(16, 2), aggregator="sum")
    total_cost = fields.Float(related="order_id.total_cost", string="Cost (USD)", store=True,
                              digits=(16, 2), aggregator="sum")
    profit = fields.Float(related="order_id.profit", string="Profit (USD)", store=True,
                          digits=(16, 2), aggregator="sum")
    margin = fields.Float(compute="_compute_margin", store=True, string="Margin", aggregator="avg",
                          help="Profit as a share of the total. Group rows show the average margin.")

    @api.depends("total_amount", "profit")
    def _compute_margin(self):
        for record in self:
            record.margin = record.profit / record.total_amount if record.total_amount else 0.0

    @api.depends("order_id")
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.order_id.display_name or "New"
