from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    account_able = fields.Boolean(string='Can be created account')