# -*- coding: utf-8 -*-

from odoo import models, fields, api


class sale_quote_template(models.Model):
    _name = "sale.quote.template"
    _inherit = "sale.quote.template"

    contract_template = fields.Many2one('sale.subscription.template', 'Contract Template',
        help="Specify a contract template in order to automatically generate a subscription when products of type subscription are sold.")

    @api.onchange('contract_template')
    def onchange_contract_template(self):
        quote_lines = [(0, 0, {
            'product_id': mand_line.product_id.id,
            'uom_id': mand_line.uom_id.id,
            'name': mand_line.name,
            'product_uom_qty': mand_line.quantity,
            'product_uom_id': mand_line.uom_id.id,
        }) for mand_line in self.contract_template.subscription_template_line_ids]
        options = [(0, 0, {
            'product_id': opt_line.product_id.id,
            'uom_id': opt_line.uom_id.id,
            'name': opt_line.name,
            'quantity': opt_line.quantity,
        }) for opt_line in self.contract_template.subscription_template_option_ids]
        self.quote_line = quote_lines
        self.options = options
        self.note = self.contract_template.description


class sale_order_line(models.Model):
    _name = "sale.order.line"
    _inherit = "sale.order.line"

    recurring_product = fields.Boolean('Recurring Product', compute="_compute_recurring")

    def _compute_recurring(self):
        for line in self:
            line.recurring_product = line.sudo().product_id.recurring_invoice
