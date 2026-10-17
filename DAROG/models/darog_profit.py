from odoo import api, fields, models


class DarogProfit(models.Model):
    _name = "darog.profit"
    _description = "Order Profit"
    _order = "id desc"

    order_id = fields.Many2one("darog.order", string="Order", ondelete="cascade")
    reciepent = fields.Char(related="order_id.reciepent_id.name", string="Recipient", store=True)
    invoice_no = fields.Integer(related="order_id.invoice_no", string="Invoice No", store=True)
    invoice_date = fields.Date(related="order_id.invoice_date", string="Invoice Date", store=True)
    order_status = fields.Selection(related="order_id.order_status", string="Status", store=True)
    total_amount = fields.Float(related="order_id.total_amount", string="Total (USD)")
    total_cost = fields.Float(compute="_compute_profit", string="Total Cost (USD)")
    profit = fields.Float(compute="_compute_profit", string="Profit (USD)")

    @api.depends("order_id.total_cost", "order_id.profit")
    def _compute_profit(self):
        for record in self:
            record.total_cost = record.order_id.total_cost
            record.profit = record.order_id.profit

    @api.depends("order_id")
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.order_id.display_name or "New"
