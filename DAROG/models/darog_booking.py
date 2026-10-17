from odoo import fields, models


class DarogBooking(models.Model):
    _name = "darog.booking"
    _description = "Booking"
    _rec_name = "booking_no"
    _order = "id"

    booking_no = fields.Char(string="Number", required=True)
    order_id = fields.Many2one("darog.order", string="Order", ondelete="cascade")
